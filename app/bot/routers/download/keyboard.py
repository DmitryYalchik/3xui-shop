from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.routers.misc.keyboard import back_button
from app.bot.utils.constants import (
    HIDDIFY_WINDOWS_LINK,
    V2RAYTUN_ANDROID_LINK,
    V2RAYTUN_IOS_LINK,
)
from app.bot.utils.navigation import NavDownload, NavSubscription, NavSupport


def platforms_keyboard(previous_callback: str = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=_("download:button:ios"),
            callback_data=NavDownload.PLATFORM_IOS,
        ),
        InlineKeyboardButton(
            text=_("download:button:android"),
            callback_data=NavDownload.PLATFORM_ANDROID,
        ),
        InlineKeyboardButton(
            text=_("download:button:windows"),
            callback_data=NavDownload.PLATFORM_WINDOWS,
        ),
    )

    back_callback = previous_callback if previous_callback else NavSupport.HOW_TO_CONNECT
    builder.row(back_button(back_callback))
    return builder.as_markup()


def download_keyboard(platform: NavDownload, url: str, key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    match platform:
        case NavDownload.PLATFORM_IOS:
            app = "v2raytun"
            download = V2RAYTUN_IOS_LINK
        case NavDownload.PLATFORM_ANDROID:
            app = "v2raytun"
            download = V2RAYTUN_ANDROID_LINK
        case _:
            app = "hiddify"
            download = HIDDIFY_WINDOWS_LINK

    connect = f"{url}connection?app={app}&key={key}"

    builder.button(text=_("download:button:download"), url=download)

    builder.button(
        text=_("download:button:connect"),
        url=connect if key else None,
        callback_data=NavSubscription.MAIN if not key else None,
    )

    builder.row(back_button(NavDownload.MAIN))
    return builder.as_markup()
