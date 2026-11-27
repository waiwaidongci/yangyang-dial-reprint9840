"""Register all SQLAlchemy tables in every entry point using this package."""

from .account import Account
from .dataset import Dataset
from .merge import MergeBook, MergeReview
from .review import Review
from .run import Run
from .seal import ShopSeal

__all__ = ['Account', 'Dataset', 'MergeBook', 'MergeReview', 'Review', 'Run', 'ShopSeal']
