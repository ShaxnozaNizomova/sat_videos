"""
Production Telegram Bot with Webhook Mode using Flask

DEPLOYMENT INSTRUCTIONS FOR RENDER:

1. Push this project to GitHub
2. Create new Web Service on Render.com
3. Connect your GitHub repository
4. Set Build Command: pip install -r requirements.txt
5. Set Start Command: python app.py
6. Add Environment Variables:
   - BOT_TOKEN: your telegram bot token
   - WEBHOOK_URL: https://your-app-name.onrender.com/webhook
   - ADMIN_ID: telegram user id for admin
   - DB_HOST: your postgres host
   - DB_PORT: 5432
   - DB_NAME: your database name
   - DB_USER: your database user
   - DB_PASSWORD: your database password
   - PORT: 8000 (or leave empty, Render sets this automatically)
7. Deploy!

The bot will automatically set webhook on startup.
"""

import logging
import os
import asyncio
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

# Initialize Flask app
app = Flask(__name__)

# Initialize Telegram Application (global)
application = None


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


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming webhook updates from Telegram."""
    try:
        # Parse incoming update
        update_data = request.get_json(force=True)
        update = Update.de_json(update_data, application.bot)
        
        # Process update asynchronously
        asyncio.run(application.process_update(update))
        
        logger.info(f"Processed update: {update.update_id}")
        return Response(status=200)
    
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return Response(status=500)


@app.route("/")
def index():
    """Health check endpoint."""
    return "Telegram Bot is running!"


@app.route("/health")
def health():
    """Health check for monitoring."""
    return {"status": "ok", "bot": "running"}


async def setup_webhook():
    """Set up the webhook for Telegram."""
    try:
        logger.info(f"Setting webhook to: {WEBHOOK_URL}")
        await application.bot.set_webhook(url=WEBHOOK_URL)
        webhook_info = await application.bot.get_webhook_info()
        logger.info(f"Webhook set successfully: {webhook_info.url}")
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        raise


async def remove_webhook():
    """Remove webhook on shutdown."""
    try:
        logger.info("Removing webhook...")
        await application.bot.delete_webhook()
        logger.info("Webhook removed")
    except Exception as e:
        logger.error(f"Failed to remove webhook: {e}")


def main():
    """Main function to start the Flask application."""
    global application
    
    logger.info("Starting Telegram bot in webhook mode...")
    
    # Setup application
    application = setup_application()
    
    # Initialize application (required for async operations)
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(setup_webhook())
    
    logger.info(f"Starting Flask server on port {PORT}...")
    
    try:
        # Run Flask app
        app.run(host="0.0.0.0", port=PORT, debug=False)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Cleanup
        loop.run_until_complete(remove_webhook())
        loop.run_until_complete(application.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
