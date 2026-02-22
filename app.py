import asyncio
import logging
import os
import threading
from flask import Flask, request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler

from config import BOT_TOKEN, WEBHOOK_URL, PORT
from database import init_db
from handlers.admin import (
    admin_add_video_handler,
    admin_command,
    admin_delete_user_callback_handler,
    admin_delete_video_callback_handler,
    admin_manage_videos_handler,
    admin_view_users_handler,
)
from handlers.user import registration_handler, video_selection_handler

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

"""
Alwaysdata WSGI entry point:
Expose the Flask instance as `application`.
"""

# Initialize Flask app
application = Flask(__name__)

# Initialize Telegram Application (global)
telegram_app = None
event_loop = None
loop_thread = None


def setup_application() -> Application:
    """Initialize and configure the Telegram application with all handlers."""
    logger.info("Setting up Telegram application...")
    
    # Initialize database
    init_db()
    
    # Build application
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    
    # Register all handlers
    telegram_app.add_handler(admin_delete_user_callback_handler, group=0)
    telegram_app.add_handler(admin_delete_video_callback_handler, group=0)
    telegram_app.add_handler(admin_add_video_handler, group=0)
    telegram_app.add_handler(admin_view_users_handler, group=0)
    telegram_app.add_handler(admin_manage_videos_handler, group=0)
    telegram_app.add_handler(CommandHandler("admin", admin_command), group=0)
    telegram_app.add_handler(registration_handler, group=1)
    telegram_app.add_handler(video_selection_handler, group=2)
    
    logger.info("Telegram application setup complete")
    return telegram_app


@application.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming webhook updates from Telegram."""
    try:
        # Parse incoming update
        update_data = request.get_json(force=True)
        update = Update.de_json(update_data, telegram_app.bot)
        
        # Process update asynchronously on the bot event loop
        future = asyncio.run_coroutine_threadsafe(
            telegram_app.process_update(update), event_loop
        )
        future.result()
        
        logger.info(f"Processed update: {update.update_id}")
        return Response(status=200)
    
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return Response(status=500)


@application.route("/")
def index():
    """Health check endpoint."""
    return "Telegram Bot is running!"


@application.route("/health")
def health():
    """Health check for monitoring."""
    return {"status": "ok", "bot": "running"}


async def setup_webhook():
    """Set up the webhook for Telegram."""
    try:
        logger.info(f"Setting webhook to: {WEBHOOK_URL}")
        await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
        webhook_info = await telegram_app.bot.get_webhook_info()
        logger.info(f"Webhook set successfully: {webhook_info.url}")
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        raise


async def remove_webhook():
    """Remove webhook on shutdown."""
    try:
        logger.info("Removing webhook...")
        await telegram_app.bot.delete_webhook()
        logger.info("Webhook removed")
    except Exception as e:
        logger.error(f"Failed to remove webhook: {e}")


def _start_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def main():
    """Main function to start the Flask application."""
    global telegram_app, event_loop, loop_thread
    
    logger.info("Starting Telegram bot in webhook mode...")
    
    # Setup application
    telegram_app = setup_application()
    
    # Start background event loop
    event_loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=_start_event_loop, args=(event_loop,), daemon=True)
    loop_thread.start()

    # Initialize and start the application
    asyncio.run_coroutine_threadsafe(telegram_app.initialize(), event_loop).result()
    asyncio.run_coroutine_threadsafe(telegram_app.start(), event_loop).result()
    asyncio.run_coroutine_threadsafe(setup_webhook(), event_loop).result()
    
    logger.info(f"Starting Flask server on port {PORT}...")
    
    try:
        # Run Flask app
        application.run(host="0.0.0.0", port=PORT, debug=False)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Cleanup
        asyncio.run_coroutine_threadsafe(remove_webhook(), event_loop).result()
        asyncio.run_coroutine_threadsafe(telegram_app.stop(), event_loop).result()
        asyncio.run_coroutine_threadsafe(telegram_app.shutdown(), event_loop).result()
        event_loop.call_soon_threadsafe(event_loop.stop)
        loop_thread.join(timeout=5)
