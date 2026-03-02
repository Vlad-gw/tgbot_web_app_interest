from aiogram import Router

from .common import router as common_router
from .income import router as income_router
from .expense import router as expense_router

router = Router()
router.include_router(common_router)
router.include_router(income_router)
router.include_router(expense_router)
