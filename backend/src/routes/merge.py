from fastapi import APIRouter, Query

from src.controllers.dependencies import Actor, Admin, Db, Writer
from src.controllers.report import report_csv
from src.schemas.merge import BookCreate, BookInfo, LocalEncode, SealDetail, SealInfo, SealSubmit
from src.schemas.merge_reviews import MergeReviewCreate, MergeReviewInfo
from src.services import merge

router = APIRouter(prefix='/merge')


@router.get('/seals', response_model=list[SealInfo])
def seals(session: Db, actor: Actor, shop: str | None = Query(None, max_length=64)):
    return merge.list_seals(session, shop)


@router.post('/seals', response_model=SealInfo, status_code=201)
def submit_seal(payload: SealSubmit, session: Db, actor: Writer):
    return merge.submit_seal(session, payload, actor)


@router.get('/seals/{shop}', response_model=SealDetail)
def seal(session: Db, actor: Actor, shop: str, version: int | None = Query(None, ge=1)):
    return merge.seal_detail(session, shop, version)


@router.get('/books', response_model=list[BookInfo])
def books(session: Db, actor: Actor):
    return merge.list_books(session, actor)


@router.post('/books', response_model=BookInfo, status_code=201)
def create_book(payload: BookCreate, session: Db, actor: Writer):
    return merge.create_book(session, payload, actor)


@router.get('/books/{book_id}')
def book_detail(book_id: int, session: Db, actor: Actor):
    return merge.book_detail(session, book_id, actor)


@router.post('/books/{book_id}/retry', response_model=BookInfo)
def retry_book(book_id: int, session: Db, actor: Writer):
    return merge.retry_book(session, book_id, actor)


@router.post('/books/{book_id}/review', response_model=MergeReviewInfo, status_code=201)
def review_book(book_id: int, payload: MergeReviewCreate, session: Db, actor: Admin):
    return merge.submit_review(session, book_id, payload, actor)


@router.post('/books/{book_id}/encode')
def encode_local(book_id: int, payload: LocalEncode, session: Db, actor: Writer):
    return merge.local_encode(session, book_id, payload, actor)


@router.get('/books/{book_id}/export/{key}')
def export_book(book_id: int, key: str, session: Db, actor: Actor):
    return report_csv(session, book_id, key, actor, table_lookup=merge.export_table)
