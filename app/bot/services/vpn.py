import logging
from datetime import datetime, timedelta, timezone

from py3xui import AsyncApi, Client
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.services.promocode import PromocodeService
from app.config import Config
from app.db.models.promocode import Promocode
from app.db.models.user import User

logger = logging.getLogger(__name__)


class VPNService:
    """
    Service for managing client data and subscriptions through the 3XUI API.

    This class provides methods for interacting with the 3XUI API to handle VPN client operations,
    such as creating, updating, retrieving, and checking client data. It also includes utility
    methods for converting traffic and duration values to the appropriate formats.

    Attributes:
        session (AsyncSession): Database session for interacting with the user model.
        subscription (str): Base subscription URL for generating user-specific keys.
        api (AsyncApi): Instance of the AsyncApi for interacting with the 3XUI API.
        promocode_service (PromocodeService): Service for managing promocodes.
    """

    def __init__(
        self, session: AsyncSession, config: Config, promocode_service: PromocodeService
    ) -> None:
        """
        Initializes the VPNService instance with database session, API configuration,
        and promocode service.

        Arguments:
            session (AsyncSession): Database session for interacting with the user model.
            config (Config): Configuration object containing API credentials and settings.
            promocode_service (PromocodeService): Service for managing promocodes.
        """
        self.session = session
        self.subscription = config.xui.SUBSCRIPTION
        self.api = AsyncApi(
            host=config.xui.HOST,
            username=config.xui.USERNAME,
            password=config.xui.PASSWORD,
            token=config.xui.TOKEN,
            use_tls_verify=False,
            logger=logging.getLogger("xui"),
        )
        self.promocode_service = promocode_service
        logger.info("VPNService initialized.")

    async def initialize(self) -> None:
        """
        Logs into the 3XUI API using the provided credentials.

        This method must be called before performing any API operations.
        """
        logger.info("Logging into 3XUI API...")
        await self.api.login()
        logger.info("Logged into 3XUI API successfully.")

    async def is_client_exists(self, user_id: int) -> Client | None:
        """
        Checks if a client exists in the 3XUI by their user ID.

        Arguments:
            user_id (int): The user ID to check for existence.

        Returns:
            Client | None: The client object if found, otherwise None.
        """
        logger.debug(f"Checking if client {user_id} exists in 3XUI.")
        client = await self.api.client.get_by_email(str(user_id))
        if client:
            logger.debug(f"Client {user_id} exists.")
        else:
            logger.debug(f"Client {user_id} not found.")
        return client

    async def get_client_data(self, user_id: int) -> dict | None:
        """
        Retrieves detailed data for a client based on the user ID.

        Arguments:
            user_id (int): The user ID of the client.

        Returns:
            dict | None: Dictionary containing client traffic and subscription data.
        """
        logger.debug(f"Starting to retrieve client data for {user_id}.")
        try:
            client: Client = await self.api.client.get_by_email(str(user_id))

            if client is None:
                logger.debug(f"No client data found for {user_id}.")
                return None

            traffic_total = client.total
            if traffic_total <= 0:
                traffic_remaining = -1
                traffic_total = -1
            else:
                traffic_remaining = client.total - (client.up + client.down)

            expiry_time = -1 if client.expiry_time == 0 else client.expiry_time

            traffic_used = client.up + client.down
            client_data = {
                "traffic_total": traffic_total,
                "traffic_remaining": traffic_remaining,
                "traffic_used": traffic_used,
                "traffic_up": client.up,
                "traffic_down": client.down,
                "expiry_time": expiry_time,
            }
            logger.debug(f"Successfully retrieved client data for {user_id}: {client_data}.")
            return client_data
        except Exception as exception:
            logger.error(f"Error retrieving client data for {user_id}: {exception}")
            return None

    async def update_client(
        self,
        user: User,
        traffic: int,
        duration: int,
        replace_traffic: bool = False,
        replace_duration: bool = False,
    ) -> None:
        """
        Updates the client’s traffic and subscription duration in the 3XUI.

        This function can either replace the existing traffic and duration values or
        add to them, based on the `replace_traffic` and `replace_duration` flags.

        Arguments:
            user (User): The user whose client data is to be updated.
            traffic (int): The traffic limit in GB to set or add for the client.
            duration (int): The duration in days to set or add to the subscription.
            replace_traffic (bool): If True, replaces the existing traffic limit.
            replace_duration (bool): If True, replaces the existing subscription duration.
        """
        logger.info(
            f"Updating client {user.user_id} with traffic={traffic} GB "
            f"and duration={duration} days."
        )

        try:
            client: Client = await self.api.client.get_by_email(str(user.user_id))

            if replace_traffic:
                new_traffic_bytes = self.gb_to_bytes(traffic)
            else:
                current_traffic_bytes = client.total
                additional_traffic_bytes = self.gb_to_bytes(traffic)
                new_traffic_bytes = current_traffic_bytes + additional_traffic_bytes

            if replace_duration:
                new_expiry_time = self.days_to_timestamp(duration)
            else:
                new_expiry_time = self.add_days_to_timestamp(client.expiry_time, duration)

            client.id = user.vpn_id
            client.expiry_time = new_expiry_time
            client.flow = "xtls-rprx-vision"
            client.limit_ip = 3
            client.sub_id = user.vpn_id
            client.total_gb = new_traffic_bytes

            await self.api.client.update(client.id, client)
            await self.api.client.reset_stats(client.inbound_id, client.email)
            logger.info(f"Client {user.user_id} updated successfully.")
        except Exception as exception:
            logger.error(f"Error updating client {user.user_id}: {exception}")

    async def create_client(self, user: User, traffic: int, duration: int) -> None:
        """
        Creates a new client in the 3XUI.

        Arguments:
            user (User): The user for whom the client is to be created.
            traffic (int): The traffic limit in GB to set for the new client.
            duration (int): The duration in days for which the subscription is valid.
        """
        logger.info(
            f"Creating new client {user.user_id} with traffic={traffic} GB "
            f"and duration={duration} days."
        )

        new_client = Client(
            email=str(user.user_id),
            enable=True,
            id=user.vpn_id,
            expiryTime=self.days_to_timestamp(duration),
            flow="xtls-rprx-vision",
            limitIp=3,  # TODO: Make a choice of the number of devices
            sub_id=user.vpn_id,
            totalGB=self.gb_to_bytes(traffic),
        )
        inbound_id = 7  # TODO: Make a server config file
        try:
            await self.api.client.add(inbound_id, [new_client])
            logger.info(f"Successfully created client for {user.user_id}.")
        except Exception as exception:
            logger.error(f"Error creating client for {user.user_id}: {exception}")

    def gb_to_bytes(self, traffic_gb: int) -> int:
        """
        Convert traffic volume from gigabytes (GB) to bytes.

        Arguments:
            traffic_gb (int): The traffic volume in gigabytes.

        Returns:
            int: The traffic volume in bytes.
        """
        bytes_in_gb = 1024**3  # 1 GB = 1024^3 bytes
        return int(traffic_gb * bytes_in_gb)

    def days_to_timestamp(self, days: int) -> int:
        """
        Convert a number of days from now to a Unix timestamp in milliseconds.

        Arguments:
            days (int): Number of days from now.

        Returns:
            int: Unix timestamp in milliseconds.
        """
        now = datetime.now(timezone.utc)
        target_time = now + timedelta(days=days)
        return int(target_time.timestamp() * 1000)

    def add_days_to_timestamp(self, timestamp: int, days: int) -> int:
        """
        Adds a number of days to a Unix timestamp in milliseconds.

        Arguments:
            timestamp (int): Current timestamp in milliseconds.
            days (int): Number of days to add.

        Returns:
            int: New Unix timestamp in milliseconds.
        """
        current_datetime = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        new_datetime = current_datetime + timedelta(days=days)
        return int(new_datetime.timestamp() * 1000)

    async def get_key(self, user_id: int) -> str:
        """
        Fetches the key from the provided URL for the given user ID.

        Arguments:
            user_id (int): The user ID for get key.

        Returns:
            str: The key extracted from the response.
        """
        logger.debug(f"Fetching key for {user_id}.")
        async with self.session() as session:
            user: User = await User.get(session, user_id=user_id)
        key = f"{self.subscription}{user.vpn_id}"
        logger.debug(f"Fetched key for {user_id}: {key}.")
        return key

    async def create_subscription(self, user_id: int, traffic: int, duration: int) -> None:
        """
        Create or update a subscription for the user.

        Arguments:
            user_id (int): The ID of the user for whom the subscription is being created or updated.
            traffic (int): The amount of traffic allocated to the user in bytes.
            duration (int): The duration of the subscription in seconds.
        """
        async with self.session() as session:
            user: User = await User.get(session, user_id=user_id)
        if await self.is_client_exists(user.user_id):
            await self.update_client(user, traffic, duration)
        else:
            await self.create_client(user, traffic, duration)

    async def activate_promocode(self, user_id: int, promocode: Promocode) -> None:
        """
        Activates a promocode for the user, updating their subscription.

        Arguments:
            user_id (int): The ID of the user to activate the promocode for.
            promocode (Promocode): The promocode object containing traffic and duration.
        """

        await self.promocode_service.activate_promocode(promocode.code, user_id)
        async with self.session() as session:
            user: User = await User.get(session, user_id=user_id)
        if await self.is_client_exists(user_id):
            await self.update_client(user, promocode.traffic, promocode.duration)
        else:
            await self.create_client(user, promocode.traffic, promocode.duration)
