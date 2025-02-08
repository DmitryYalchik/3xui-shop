import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.models import ClientData, ServicesContainer, SubscriptionData
from app.bot.utils.navigation import NavSubscription
from app.db.models import Server, User

from .keyboard import (
    devices_keyboard,
    duration_keyboard,
    payment_method_keyboard,
    subscription_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name=__name__)


async def show_subscription(
    callback: CallbackQuery,
    client_data: ClientData | None,
    callback_data: SubscriptionData,
) -> None:
    text = ""
    if client_data:
        if client_data.has_subscription_expired:
            text = _("subscription:message:expired")
        else:
            text = _("subscription:message:active").format(
                devices=client_data.max_devices,
                expiry_time=client_data.expiry_time,
            )
    else:
        text = _("subscription:message:not_active")

    await callback.message.edit_text(
        text=text, reply_markup=subscription_keyboard(client_data, callback_data)
    )


@router.callback_query(F.data == NavSubscription.MAIN)
async def callback_subscription(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    services: ServicesContainer,
) -> None:
    logger.info(f"User {user.tg_id} opened subscription page.")
    await state.set_state(None)
    client_data = await services.vpn.get_client_data(user)
    callback_data = SubscriptionData(state=NavSubscription.PROCESS, user_id=user.tg_id)
    await show_subscription(callback, client_data, callback_data)


@router.callback_query(SubscriptionData.filter(F.state == NavSubscription.EXTEND))
async def callback_subscription_extend(
    callback: CallbackQuery,
    user: User,
    callback_data: SubscriptionData,
    services: ServicesContainer,
) -> None:
    logger.info(f"User {user.tg_id} started extend subscription.")
    client = await services.vpn.is_client_exists(user)
    callback_data.devices = await services.vpn.get_limit_ip(user, client)
    callback_data.state = NavSubscription.DURATION
    callback_data.is_extend = True
    await callback.message.edit_text(
        text=_("subscription:message:duration"),
        reply_markup=duration_keyboard(services.plan, callback_data),
    )


@router.callback_query(SubscriptionData.filter(F.state == NavSubscription.PROCESS))
async def callback_subscription_process(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    callback_data: SubscriptionData,
    services: ServicesContainer,
) -> None:
    logger.info(f"User {user.tg_id} started subscription process.")
    server = await Server.get_available(session)

    if not server:
        await services.notification.show_popup(
            callback=callback,
            text=_("subscription:popup:no_available_servers"),
            cache_time=120,
        )
        return

    callback_data.state = NavSubscription.DEVICES
    await callback.message.edit_text(
        text=_("subscription:message:devices"),
        reply_markup=devices_keyboard(services.plan, callback_data),
    )


@router.callback_query(SubscriptionData.filter(F.state == NavSubscription.DEVICES))
async def callback_devices_selected(
    callback: CallbackQuery,
    user: User,
    callback_data: SubscriptionData,
    services: ServicesContainer,
) -> None:
    logger.info(f"User {user.tg_id} selected devices: {callback_data.devices}")
    callback_data.state = NavSubscription.DURATION
    await callback.message.edit_text(
        text=_("subscription:message:duration"),
        reply_markup=duration_keyboard(services.plan, callback_data),
    )


@router.callback_query(SubscriptionData.filter(F.state == NavSubscription.DURATION))
async def callback_duration_selected(
    callback: CallbackQuery,
    user: User,
    callback_data: SubscriptionData,
    services: ServicesContainer,
) -> None:
    logger.info(f"User {user.tg_id} selected duration: {callback_data.duration}")
    callback_data.state = NavSubscription.PAY
    await callback.message.edit_text(
        text=_("subscription:message:payment_method"),
        reply_markup=payment_method_keyboard(
            services.payment.gateways, callback_data, services.plan
        ),
    )
