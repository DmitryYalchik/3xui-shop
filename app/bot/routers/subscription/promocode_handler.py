import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.models import ServicesContainer
from app.bot.routers.misc.keyboard import back_keyboard
from app.bot.utils.constants import MAIN_MESSAGE_ID_KEY
from app.bot.utils.navigation import NavSubscription
from app.db.models import Promocode, User

logger = logging.getLogger(__name__)
router = Router(name=__name__)


class ActivatePromocodeStates(StatesGroup):
    promocode_input = State()


@router.callback_query(F.data == NavSubscription.PROMOCODE)
async def callback_promocode(callback: CallbackQuery, user: User, state: FSMContext) -> None:
    logger.info(f"User {user.tg_id} started activating promocode.")
    await state.set_state(ActivatePromocodeStates.promocode_input)
    await callback.message.edit_text(
        text=_("promocode:message:main"),
        reply_markup=back_keyboard(NavSubscription.MAIN),
    )


@router.message(ActivatePromocodeStates.promocode_input)
async def handle_promocode_input(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    services: ServicesContainer,
) -> None:
    input_promocode = message.text.strip()
    logger.info(f"User {user.tg_id} entered promocode: {input_promocode} for activating.")

    promocode = await Promocode.get(session, input_promocode)
    if promocode and not promocode.is_activated:
        success = await services.vpn.activate_promocode(user, promocode)
        message_id = await state.get_value(MAIN_MESSAGE_ID_KEY)
        if success:
            await message.bot.edit_message_text(
                text=_("promocode:message:activated_success").format(
                    promocode=input_promocode,
                    duration=services.plan.convert_days_to_period(promocode.duration),
                ),
                chat_id=message.chat.id,
                message_id=message_id,
                reply_markup=back_keyboard(NavSubscription.MAIN),
            )
        else:
            text = _("promocode:notification:activate_failed")
            await services.notification.notify_by_message(message, text, 5)
    else:
        text = _("promocode:notification:activate_invalid").format(promocode=input_promocode)
        await services.notification.notify_by_message(message, text, 5)
