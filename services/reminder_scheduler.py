# services/reminder_scheduler.py

from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database.db import db


scheduler = AsyncIOScheduler()


def build_reminder_text(first_name: str | None = None) -> str:
    name_part = f", {first_name}" if first_name else ""
    return (
        f"⏰ Напоминание{name_part}\n\n"
        "Не забудьте добавить транзакции за сегодня.\n"
        "Это поможет сохранить точную аналитику и баланс."
    )


async def process_daily_transaction_reminders(bot) -> None:
    now = datetime.now()
    current_date = now.date()
    current_hhmm = now.strftime("%H:%M")

    reminders = await db.get_users_with_active_reminders()

    for reminder in reminders:
        try:
            remind_time = reminder["remind_time"]
            if not remind_time:
                continue

            remind_hhmm = remind_time.strftime("%H:%M")
            if remind_hhmm != current_hhmm:
                continue

            last_sent_date = reminder["last_sent_date"]
            if last_sent_date == current_date:
                continue

            user_id = reminder["user_id"]
            telegram_id = reminder["telegram_id"]
            first_name = reminder["first_name"]

            has_transactions = await db.has_transactions_for_date(user_id, current_date)
            if has_transactions:
                continue

            await bot.send_message(
                chat_id=telegram_id,
                text=build_reminder_text(first_name),
            )

            await db.mark_reminder_sent(user_id, current_date)

        except Exception as e:
            print(f"Ошибка при отправке напоминания user_id={reminder.get('user_id')}: {e}")


def start_scheduler(bot) -> None:
    if scheduler.running:
        return

    scheduler.add_job(
        process_daily_transaction_reminders,
        trigger="interval",
        minutes=1,
        args=[bot],
        id="daily_transaction_reminders_checker",
        replace_existing=True,
    )
    scheduler.start()


async def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)