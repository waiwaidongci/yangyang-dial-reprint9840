"""Shared codebook built from two shops' sealed aggregates.

Lifecycle
---------
* A shop submits a sealed aggregate as a new ``version``.  Seals are
  append-only: a supplementary report ("补报") is a new version, never an edit of
  an older one, so a merge that already referenced a version keeps reading the
  exact aggregate it started with.
* A merge book pins the ``(shop, version)`` pair of both shops at the moment it
  starts.  It only begins once both seals exist, and it always computes from the
  pinned versions even if newer seals arrive while it runs.
* The unique ``(shop_low, version_low, shop_high, version_high)`` constraint makes
  creation idempotent: retrying never adds a second book for the same versions.
* A book is marked ``ready`` only after the whole codebook is computed.  An
  interrupted run stays ``calculating``; retrying reloads the pinned versions and
  finishes without changing them.
"""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.constants.workflow import Decision, MergeStatus, Role
from src.domain.evaluation import holdout_diagnostics
from src.domain.merge import apply_codebook, build_codebook, merge_seals, normalize_shop, seal_from_rows, validate_seal
from src.domain.merge_report import summarize_merge
from src.domain.records import normalize_rows
from src.domain.reports import comparison_table, review_queue, trace_table
from src.domain.settings import SETTINGS
from src.models.merge import MergeBook, MergeReview
from src.models.seal import ShopSeal
from src.utils.time import utc_stamp

SMOOTHING = next(item for item in SETTINGS if item['key'] == 'smoothing')


def _checksum(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def seal_info(seal: ShopSeal) -> dict:
    return {
        'id': seal.id,
        'shop': seal.shop,
        'version': seal.version,
        'rows': seal.rows,
        'reprints': seal.reprints,
        'batches': len(seal.payload.get('batches', {})),
        'checksum': _checksum(seal.payload),
        'created_at': seal.created_at,
    }


def _latest_seal(session, shop, version):
    return session.scalar(
        select(ShopSeal).where(ShopSeal.shop == shop, ShopSeal.version == version)
    )


def _body(seal: dict) -> dict:
    """Aggregate content without its version, for idempotent resubmission."""

    return {key: value for key, value in seal.items() if key != 'version'}


def list_seals(session, shop=None):
    statement = select(ShopSeal).order_by(ShopSeal.shop, ShopSeal.version.desc())
    if shop:
        statement = statement.where(ShopSeal.shop == normalize_shop(shop))
    return [seal_info(seal) for seal in session.scalars(statement)]


def seal_detail(session, shop, version=None):
    shop = normalize_shop(shop)
    if version is None:
        seal = session.scalar(
            select(ShopSeal).where(ShopSeal.shop == shop).order_by(ShopSeal.version.desc())
        )
    else:
        seal = _latest_seal(session, shop, version)
    if seal is None:
        raise LookupError('找不到该车间的封账数')
    return {**seal_info(seal), 'payload': seal.payload}


def submit_seal(session, payload, actor):
    if payload.csv is not None and payload.payload is not None:
        raise ValueError('请提交本地台账或封账合计中的一种，不要同时提交。')
    if payload.csv is not None:
        from src.utils.csv_files import read_rows
        from src.domain.project import SPEC
        rows = read_rows(payload.csv, SPEC['columns'])
        shop = normalize_shop(payload.shop) if payload.shop else None
        if shop is None:
            raise ValueError('请填写车间编号。')
        seal = seal_from_rows(rows, shop)
    elif payload.payload is not None:
        seal = validate_seal(payload.payload)
        if payload.shop and normalize_shop(payload.shop) != seal['shop']:
            raise ValueError('提交的车间编号与封账合计不一致。')
    else:
        raise ValueError('请提交本地台账 CSV 或封账合计。')

    shop = seal['shop']
    if payload.version is not None:
        version = payload.version
        if version < 1:
            raise ValueError('封账版次须为正整数。')
    else:
        latest = session.scalar(
            select(ShopSeal).where(ShopSeal.shop == shop).order_by(ShopSeal.version.desc())
        )
        if latest is not None and _body(latest.payload) == seal:
            # identical resubmission without a version is a harmless retry
            return seal_info(latest)
        version = (latest.version if latest is not None else 0) + 1

    seal = {**seal, 'version': version}
    existing = _latest_seal(session, shop, version)
    if existing is not None:
        if existing.payload == seal:
            return seal_info(existing)
        raise HTTPException(409, '该车间同一封账版次内容不同，请改用新的版次补报')

    row = ShopSeal(shop=shop, version=version, rows=seal['rows'], reprints=seal['reprints'],
                   payload=seal, created_by=actor.id, created_at=utc_stamp())
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _latest_seal(session, shop, version)
        if existing is not None and existing.payload == seal:
            return seal_info(existing)
        raise HTTPException(409, '该车间同一封账版次内容不同，请改用新的版次补报') from None
    return seal_info(row)


def _select_pair(session, requested):
    """Resolve the pinned (shop, version) pair for a new book."""

    if requested:
        pairs = []
        for item in requested:
            shop = normalize_shop(item.shop)
            version = item.version
            if version is None:
                latest = session.scalar(
                    select(ShopSeal.version).where(ShopSeal.shop == shop).order_by(ShopSeal.version.desc())
                )
                if latest is None:
                    raise ValueError(f'车间 {shop} 尚未交封账数，请等两边交齐后再开算。')
                version = latest
            seal = _latest_seal(session, shop, version)
            if seal is None:
                raise ValueError(f'车间 {shop} 的封账版次 {version} 不存在，请等两边交齐后再开算。')
            pairs.append((shop, version))
    else:
        shops = list(session.scalars(select(ShopSeal.shop).distinct().order_by(ShopSeal.shop)))
        if len(shops) != 2:
            raise ValueError('合册需要恰好两个车间的封账数，请等两边交齐后再开算。')
        pairs = []
        for shop in shops:
            latest = session.scalar(
                select(ShopSeal.version).where(ShopSeal.shop == shop).order_by(ShopSeal.version.desc())
            )
            pairs.append((shop, latest))

    if len({shop for shop, _ in pairs}) != 2 or len(pairs) != 2:
        raise ValueError('合册需要两个不同车间的封账版次。')
    return tuple(sorted(pairs))


def _compute(session, book):
    low = _latest_seal(session, book.shop_low, book.version_low)
    high = _latest_seal(session, book.shop_high, book.version_high)
    if low is None or high is None:
        raise ValueError('开算时的封账版次已不存在，无法按原版次恢复。')
    merged = merge_seals([low.payload, high.payload])
    codebook = build_codebook(merged, book.smoothing)
    result = summarize_merge(merged, codebook)
    result['versions'] = {book.shop_low: book.version_low, book.shop_high: book.version_high}
    book.result = result
    book.error = None
    book.status = MergeStatus.READY
    book.updated_at = utc_stamp()


def book_info(book, review):
    return {
        'id': book.id,
        'label': book.label,
        'status': book.status,
        'smoothing': book.smoothing,
        'versions': {
            book.shop_low: book.version_low,
            book.shop_high: book.version_high,
        },
        'seals': [
            {'shop': book.shop_low, 'version': book.version_low},
            {'shop': book.shop_high, 'version': book.version_high},
        ],
        'created_at': book.created_at,
        'updated_at': book.updated_at,
        'decision': review.decision if review else None,
    }


def list_books(session, actor):
    statement = select(MergeBook, MergeReview).outerjoin(MergeReview, MergeBook.id == MergeReview.book_id)
    if actor.role == Role.VIEWER:
        statement = statement.where(MergeBook.status == MergeStatus.APPROVED)
    statement = statement.order_by(MergeBook.id.desc()).limit(100)
    return [book_info(book, review) for book, review in session.execute(statement)]


def get_book(session, book_id, actor):
    book = session.get(MergeBook, book_id)
    review = session.get(MergeReview, book_id)
    if book is None or (actor.role == Role.VIEWER and (not review or review.decision != Decision.APPROVED)):
        raise LookupError('找不到可查看的编码册')
    return book, review


def book_detail(session, book_id, actor):
    book, review = get_book(session, book_id, actor)
    return {
        **book_info(book, review),
        'result': book.result,
        'error': book.error,
        'review': review_info(review) if review else None,
    }


def review_info(review):
    return {'book_id': review.book_id, 'decision': review.decision, 'note': review.note,
            'created_at': review.created_at}


def create_book(session, payload, actor):
    smoothing = float(SMOOTHING['default'])
    low, high = _select_pair(session, payload.seals)
    (shop_low, version_low), (shop_high, version_high) = low, high

    existing = session.scalar(
        select(MergeBook).where(
            MergeBook.shop_low == shop_low, MergeBook.version_low == version_low,
            MergeBook.shop_high == shop_high, MergeBook.version_high == version_high,
        )
    )
    if existing is not None:
        return _finish_or_return(session, existing)

    book = MergeBook(
        label=payload.label, shop_low=shop_low, version_low=version_low,
        shop_high=shop_high, version_high=version_high, status=MergeStatus.CALCULATING,
        smoothing=smoothing, result=None, error=None, created_by=actor.id,
        created_at=utc_stamp(), updated_at=utc_stamp(),
    )
    session.add(book)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(MergeBook).where(
                MergeBook.shop_low == shop_low, MergeBook.version_low == version_low,
                MergeBook.shop_high == shop_high, MergeBook.version_high == version_high,
            )
        )
        if existing is None:
            raise
        return _finish_or_return(session, existing)
    return _finish_or_return(session, book)


def _finish_or_return(session, book):
    """Complete a book that has not reached a reviewable state yet."""

    if book.status in (MergeStatus.READY, MergeStatus.APPROVED, MergeStatus.REJECTED):
        session.refresh(book)
        return book_info(book, session.get(MergeReview, book.id))
    book.status = MergeStatus.CALCULATING
    book.updated_at = utc_stamp()
    session.commit()
    try:
        _compute(session, book)
    except ValueError as error:
        book.status = MergeStatus.FAILED
        book.error = str(error)
        book.updated_at = utc_stamp()
        session.commit()
        raise
    session.commit()
    return book_info(book, session.get(MergeReview, book.id))


def retry_book(session, book_id, actor):
    book = session.get(MergeBook, book_id)
    if book is None:
        raise LookupError('找不到该编码册')
    if book.status in (MergeStatus.APPROVED, MergeStatus.REJECTED):
        raise HTTPException(409, '已复核的编码册不能重算')
    return _finish_or_return(session, book)


def submit_review(session, book_id, payload, actor):
    book = session.get(MergeBook, book_id)
    if book is None or book.status != MergeStatus.READY:
        raise HTTPException(409, '仅可复核计算完成、尚未复核的编码册')
    if session.get(MergeReview, book_id) is not None:
        raise HTTPException(409, '仅可复核一次')
    review = MergeReview(book_id=book_id, reviewer_id=actor.id, decision=payload.decision,
                         note=payload.note, created_at=utc_stamp())
    book.status = MergeStatus.APPROVED if payload.decision == Decision.APPROVED else MergeStatus.REJECTED
    book.updated_at = utc_stamp()
    session.add(review)
    session.commit()
    return review_info(review)


def export_table(session, book_id, key, actor):
    book, review = get_book(session, book_id, actor)
    if review is None or review.decision != Decision.APPROVED:
        raise HTTPException(409, '复核通过后可下载正式 CSV')
    for table in book.result['tables']:
        if table['key'] == key:
            return table
    raise LookupError('找不到结果表')


def local_encode(session, book_id, payload, actor):
    """Apply an approved book to locally held rows without uploading the rows."""

    book, review = get_book(session, book_id, actor)
    if review is None or review.decision != Decision.APPROVED:
        raise HTTPException(409, '复核通过后才能按册编码本车间首件')
    normalize_shop(payload.shop)
    normalized = normalize_rows([dict(row) for row in payload.rows], require_history=False)
    ordered = sorted(normalized, key=lambda row: row['id'])
    codebook = codebook_for(session, book)
    holdout = apply_codebook(codebook, [row for row in ordered if row['split'] == 'holdout'])
    pending = apply_codebook(codebook, [row for row in ordered if row['split'] == 'pending'])
    queue, prioritized = review_queue(pending, payload.review_threshold)
    tables = []
    warnings = []
    if holdout:
        comparison, holdout_warnings = holdout_diagnostics(holdout)
        tables.append(comparison_table(comparison))
        tables.append(trace_table('holdout_encodings', '留出件编码明细', holdout))
        warnings.extend(holdout_warnings)
    tables.append(queue)
    return {
        'book_id': book.id,
        'shop': payload.shop,
        'versions': book.result.get('versions', {}),
        'prioritized': prioritized,
        'tables': tables,
        'warnings': warnings,
    }


def codebook_for(session, book):
    low = _latest_seal(session, book.shop_low, book.version_low)
    high = _latest_seal(session, book.shop_high, book.version_high)
    if low is None or high is None:
        raise LookupError('开算时的封账版次已不存在，无法按原版次编码。')
    return build_codebook(merge_seals([low.payload, high.payload]), book.smoothing)


__all__ = [
    'book_detail', 'book_info', 'create_book', 'export_table', 'get_book',
    'list_books', 'list_seals', 'local_encode', 'retry_book', 'seal_detail', 'seal_info',
    'submit_review', 'submit_seal',
]
