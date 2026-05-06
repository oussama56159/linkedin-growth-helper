"""
Telegram bot for sending suggestions and handling approve/reject decisions.
Uses the Telegram Bot API (free, no library needed beyond requests).

Setup:
  1. Message @BotFather on Telegram → /newbot → get your token
  2. Message your bot once, then run get_chat_id() to find your chat_id
  3. Fill in settings.yaml with bot_token and chat_id
"""

import logging
import requests
import json
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    def __init__(self, config: Dict[str, Any], db):
        tg_cfg = config.get("telegram", {})
        self.token = tg_cfg.get("bot_token", "")
        self.chat_id = tg_cfg.get("chat_id", "")
        self.db = db

        if not self.token or self.token == "YOUR_TELEGRAM_BOT_TOKEN":
            logger.warning("Telegram bot token not configured.")

    # ── Sending ────────────────────────────────────────────────────────────

    def send_post_suggestion(self, suggestion: Dict[str, Any]) -> Optional[int]:
        """Send a post engagement suggestion with Approve/Reject buttons."""
        sid = suggestion["id"]
        stype = suggestion["suggestion_type"].upper()
        url = suggestion["target_url"]
        summary = suggestion.get("target_summary", "No summary available")
        reason = suggestion.get("reason", "")
        draft = suggestion.get("comment_draft", "")

        text = (
            f"📌 *Suggestion #{sid}* — {stype}\n\n"
            f"🔗 [View Post]({url})\n\n"
            f"📝 *Summary:*\n{summary[:300]}{'...' if len(summary) > 300 else ''}\n\n"
            f"💡 *Reason:* {reason}\n"
        )

        if draft:
            text += f"\n✍️ *Comment Draft:*\n_{draft}_\n"

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": f"approve_{sid}"},
                    {"text": "❌ Reject", "callback_data": f"reject_{sid}"},
                ]
            ]
        }

        return self._send_message(text, reply_markup=keyboard)

    def send_profile_suggestion(self, suggestion: Dict[str, Any]) -> Optional[int]:
        """Send a connection suggestion with Approve/Reject buttons."""
        sid = suggestion["id"]
        stype = suggestion.get("suggestion_type", "connect")
        url = suggestion["target_url"]
        summary = suggestion.get("target_summary", "No summary available")
        reason = suggestion.get("reason", "")
        title = "Follow Suggestion" if stype == "follow" else "Connection Suggestion"
        view_label = "View Page" if stype == "follow" else "View Profile"
        approve_label = "Follow" if stype == "follow" else "Connect"
        summary_label = "Page" if stype == "follow" else "Profile"

        text = (
            f"🤝 *{title} #{sid}*\n\n"
            f"🔗 [{view_label}]({url})\n\n"
            f"👤 *{summary_label}:*\n{summary}\n\n"
            f"💡 *Reason:* {reason}\n"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": f"✅ {approve_label}", "callback_data": f"approve_{sid}"},
                    {"text": "❌ Skip", "callback_data": f"reject_{sid}"},
                ]
            ]
        }

        return self._send_message(text, reply_markup=keyboard)

    def send_daily_summary(self, stats: Dict[str, Any]):
        """Send a daily activity summary."""
        text = (
            "📊 *Daily LinkedIn Activity Summary*\n\n"
            f"👍 Likes: {stats.get('likes', 0)}\n"
            f"💬 Comments: {stats.get('comments', 0)}\n"
            f"🔁 Reposts: {stats.get('reposts', 0)}\n"
            f"🤝 Connections: {stats.get('connections', 0)}\n\n"
            f"📋 Pending approvals: {stats.get('pending', 0)}\n"
            f"✅ Executed today: {stats.get('executed', 0)}\n"
        )
        self._send_message(text)

    def send_batch_suggestions(
        self,
        post_suggestions: List[Dict],
        profile_suggestions: List[Dict],
    ):
        """Send all pending suggestions in one batch."""
        if not post_suggestions and not profile_suggestions:
            self._send_message("ℹ️ No new suggestions this run.")
            return

        # Header
        total = len(post_suggestions) + len(profile_suggestions)
        self._send_message(
            f"🚀 *New LinkedIn Suggestions* ({total} total)\n"
            f"Posts: {len(post_suggestions)} | Profiles: {len(profile_suggestions)}"
        )

        for s in post_suggestions:
            msg_id = self.send_post_suggestion(s)
            if msg_id:
                self.db.update_suggestion_status(s["id"], "pending", msg_id)

        for s in profile_suggestions:
            msg_id = self.send_profile_suggestion(s)
            if msg_id:
                self.db.update_suggestion_status(s["id"], "pending", msg_id)

    # ── Receiving (polling) ────────────────────────────────────────────────

    def poll_updates(self, offset: int = 0) -> List[Dict]:
        """Poll for new Telegram updates (callback queries from buttons)."""
        resp = self._api_call(
            "getUpdates",
            params={
                "offset": offset,
                "timeout": 10,
                "allowed_updates": json.dumps(["callback_query"]),
            },
        )
        if resp and resp.get("ok"):
            return resp.get("result", [])
        return []

    def process_callback(self, callback: Dict) -> Optional[Dict]:
        """
        Process an approve/reject callback from Telegram.
        Returns dict with suggestion_id and decision, or None.
        """
        query = callback.get("callback_query", {})
        data = query.get("data", "")
        query_id = query.get("id")

        if not data or "_" not in data:
            return None

        action, sid_str = data.split("_", 1)
        try:
            suggestion_id = int(sid_str)
        except ValueError:
            return None

        # Acknowledge the button press
        self._api_call(
            "answerCallbackQuery",
            json_data={
                "callback_query_id": query_id,
                "text": f"Suggestion #{suggestion_id} processed",
                "show_alert": False,
            },
        )

        decision = "approved" if action == "approve" else "rejected"
        logger.info("Telegram decision: suggestion #%d -> %s", suggestion_id, decision)

        return {"suggestion_id": suggestion_id, "decision": decision}

    def update_message_status(self, message_id: int, status: str, suggestion_id: int):
        """Edit the original suggestion message to show its status."""
        status_emoji = {"approved": "✅", "rejected": "❌", "executed": "🎯"}.get(status, "⏳")
        self._api_call(
            "editMessageReplyMarkup",
            json_data={
                "chat_id": self.chat_id,
                "message_id": message_id,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": f"{status_emoji} {status.upper()}", "callback_data": "done"}]
                    ]
                },
            },
        )

    # ── Internal ───────────────────────────────────────────────────────────

    def _send_message(
        self,
        text: str,
        reply_markup: Optional[Dict] = None,
    ) -> Optional[int]:
        """Send a Telegram message. Returns message_id on success."""
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        resp = self._api_call("sendMessage", json_data=payload)
        if resp and resp.get("ok"):
            return resp["result"]["message_id"]
        logger.error("Failed to send Telegram message: %s", resp)
        return None

    def _api_call(
        self,
        method: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """Make a Telegram Bot API call."""
        if not self.token or self.token == "YOUR_TELEGRAM_BOT_TOKEN":
            logger.warning("Telegram not configured, skipping API call: %s", method)
            return None

        url = TELEGRAM_API.format(token=self.token, method=method)
        try:
            if json_data:
                resp = requests.post(url, json=json_data, timeout=15)
            else:
                resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error("Telegram API error (%s): %s", method, e)
            return None


def get_chat_id(bot_token: str) -> Optional[str]:
    """
    Helper to find your chat_id after messaging your bot.
    Run this once during setup.
    """
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    resp = requests.get(url, timeout=10)
    data = resp.json()
    updates = data.get("result", [])
    if updates:
        chat_id = updates[-1]["message"]["chat"]["id"]
        print(f"Your chat_id is: {chat_id}")
        return str(chat_id)
    print("No messages found. Send a message to your bot first, then run this again.")
    return None
