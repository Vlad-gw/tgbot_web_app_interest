# handlers/import_statement.py

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database.repository import TransactionRepository
from services.bank_import.importer import parse_statement_file, import_parsed_operations
from services.bank_import.preview import format_statement_preview
from states.transaction_states import StatementImportState
from utils.keyboards import main_menu, back_keyboard

router = Router()

TEMP_IMPORT_DIR = Path("temp/imports")
TEMP_IMPORT_DIR.mkdir(parents=True, exist_ok=True)


def bank_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🅰️ Альфа-Банк", callback_data="stmt_bank_alfa")],
            [InlineKeyboardButton(text="🟢 Сбербанк", callback_data="stmt_bank_sber")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="stmt_import_cancel")],
        ]
    )


def import_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Импортировать", callback_data="stmt_import_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="stmt_import_cancel")],
        ]
    )


async def _cleanup_temp_file_from_state(state: FSMContext) -> None:
    data = await state.get_data()
    temp_path = data.get("statement_temp_path")

    if temp_path:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except Exception:
            pass


@router.message(F.text == "📥 Импорт выписки")
async def start_statement_import(message: Message, state: FSMContext) -> None:
    await _cleanup_temp_file_from_state(state)
    await state.clear()
    await state.set_state(StatementImportState.choosing_bank)

    await message.answer(
        "Выбери банк для импорта выписки:",
        reply_markup=bank_choice_keyboard(),
    )


@router.callback_query(F.data == "stmt_import_cancel")
async def cancel_statement_import(callback: CallbackQuery, state: FSMContext) -> None:
    await _cleanup_temp_file_from_state(state)
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.answer("Импорт выписки отменён.", reply_markup=main_menu())


@router.callback_query(F.data.startswith("stmt_bank_"), StatementImportState.choosing_bank)
async def choose_statement_bank(callback: CallbackQuery, state: FSMContext) -> None:
    bank_name = callback.data.removeprefix("stmt_bank_")

    await state.update_data(statement_bank=bank_name)
    await state.set_state(StatementImportState.waiting_for_file)

    if bank_name == "alfa":
        text = (
            "Отправь PDF-выписку Альфа-Банка одним файлом.\n\n"
            "Поддерживается только <b>PDF</b>."
        )
    elif bank_name == "sber":
        text = (
            "Отправь PDF-выписку Сбербанка одним файлом.\n\n"
            "Поддерживается только <b>PDF</b>."
        )
    else:
        text = "❌ Этот банк пока не поддерживается."

    await callback.answer()
    await callback.message.answer(text, reply_markup=back_keyboard())


@router.message(StatementImportState.waiting_for_file, F.document)
async def receive_statement_file(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    bank_name = data.get("statement_bank")

    if bank_name not in {"alfa", "sber"}:
        await message.answer(
            "❌ Этот банк пока не поддерживается.",
            reply_markup=main_menu(),
        )
        await state.clear()
        return

    document = message.document
    file_name = document.file_name or "statement.pdf"

    if not file_name.lower().endswith(".pdf"):
        await message.answer(
            "Сейчас поддерживается только PDF-файл.",
            reply_markup=back_keyboard(),
        )
        return

    telegram_id = message.from_user.id
    user_id = await TransactionRepository.get_user_id(telegram_id)
    if not user_id:
        await message.answer("Сначала нажми /start, чтобы зарегистрироваться.")
        return

    temp_path = TEMP_IMPORT_DIR / f"{uuid4().hex}_{file_name}"
    await message.bot.download(document, destination=temp_path)

    await message.answer("Файл получен. Разбираю выписку...")

    try:
        parsed = parse_statement_file(bank_name, temp_path)
    except NotImplementedError as e:
        temp_path.unlink(missing_ok=True)
        await message.answer(str(e), reply_markup=main_menu())
        await state.clear()
        return
    except Exception as e:
        temp_path.unlink(missing_ok=True)
        await message.answer(
            "Не удалось разобрать выписку.\n\n"
            f"Ошибка: <b>{e}</b>",
            reply_markup=main_menu(),
        )
        await state.clear()
        return

    operations = parsed.get("operations", [])
    if not operations:
        temp_path.unlink(missing_ok=True)
        await message.answer(
            "В выписке не найдено операций для импорта.",
            reply_markup=main_menu(),
        )
        await state.clear()
        return

    await state.update_data(
        statement_temp_path=str(temp_path),
        statement_file_name=file_name,
        statement_file_type="pdf",
        statement_parsed=parsed,
    )
    await state.set_state(StatementImportState.confirming_import)

    await message.answer(
        format_statement_preview(parsed),
        reply_markup=import_confirm_keyboard(),
    )


@router.message(StatementImportState.waiting_for_file)
async def waiting_statement_file_text(message: Message) -> None:
    await message.answer("Пожалуйста, отправь PDF-файл выписки документом.")


@router.callback_query(F.data == "stmt_import_confirm", StatementImportState.confirming_import)
async def confirm_statement_import(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()

    parsed = data.get("statement_parsed")
    file_name = data.get("statement_file_name", "statement.pdf")
    file_type = data.get("statement_file_type", "pdf")

    telegram_id = callback.from_user.id
    user_id = await TransactionRepository.get_user_id(telegram_id)
    if not user_id:
        await callback.message.answer("Сначала нажми /start, чтобы зарегистрироваться.")
        return

    if not parsed:
        await callback.answer("Нет данных для импорта", show_alert=True)
        return

    result = await import_parsed_operations(
        user_id=user_id,
        file_name=file_name,
        file_type=file_type,
        parsed=parsed,
    )

    await _cleanup_temp_file_from_state(state)
    await state.clear()
    await callback.answer("Импорт завершён")

    await callback.message.answer(
        "✅ <b>Импорт завершён</b>\n\n"
        f"<b>Всего строк операций в выписке:</b> {result['total_rows_found']}\n"
        f"<b>Подготовлено к импорту:</b> {result['ready_to_import']}\n"
        f"<b>Импортировано:</b> {result['total_imported']}\n"
        f"<b>Дубликатов пропущено:</b> {result['total_duplicates']}\n"
        f"<b>Пропущено служебных операций:</b> {result['total_skipped']}",
        reply_markup=main_menu(),
    )


@router.message(F.text == "🔙 Назад")
async def back_from_statement_import(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state not in {
        StatementImportState.choosing_bank.state,
        StatementImportState.waiting_for_file.state,
        StatementImportState.confirming_import.state,
    }:
        return

    await _cleanup_temp_file_from_state(state)
    await state.clear()
    await message.answer("Возврат в главное меню.", reply_markup=main_menu())