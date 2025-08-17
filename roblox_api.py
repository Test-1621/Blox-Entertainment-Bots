import aiohttp
import asyncio
from config import Config

class RobloxAPI:
    """Handles interactions with the Roblox API"""

    def __init__(self):
        self.session = None

    async def _get_session(self):
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self.session

    # ===== Existing user methods =====
    async def get_user_by_username(self, username):
        try:
            session = await self._get_session()
            url = Config.ROBLOX_USERNAME_API
            payload = {"usernames": [username], "excludeBannedUsers": True}
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    users = data.get('data', [])
                    if users:
                        user = users[0]
                        return {
                            'id': user.get('id'),
                            'name': user.get('name'),
                            'displayName': user.get('displayName')
                        }
                    return None
                else:
                    print(f"Roblox API error for username lookup: {response.status}")
                    return None
        except Exception as e:
            print(f"Error fetching Roblox user by username: {e}")
            return None

    async def get_user_bio(self, user_id):
        try:
            session = await self._get_session()
            url = Config.ROBLOX_USER_API.format(user_id=user_id)
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('description', '')
                elif response.status == 404:
                    print(f"Roblox user {user_id} not found")
                    return None
                else:
                    print(f"Roblox API error for user {user_id}: {response.status}")
                    return None
        except Exception as e:
            print(f"Error fetching Roblox user bio: {e}")
            return None

    async def get_user_details(self, user_id):
        try:
            session = await self._get_session()
            url = Config.ROBLOX_USER_API.format(user_id=user_id)
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'id': data.get('id'),
                        'name': data.get('name'),
                        'displayName': data.get('displayName'),
                        'description': data.get('description', ''),
                        'created': data.get('created'),
                        'isBanned': data.get('isBanned', False)
                    }
                else:
                    print(f"Roblox API error for user details: {response.status}")
                    return None
        except Exception as e:
            print(f"Error fetching Roblox user details: {e}")
            return None

    # ===== Advertisement-related methods =====
    async def get_game_info(self, link: str):
        """Fetch Roblox game info by link"""
        try:
            place_id = int(link.rstrip("/").split("/games/")[1].split("/")[0])
        except Exception:
            return None
        url = f"https://games.roblox.com/v1/games/multiget-place-details?placeIds={place_id}"
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data:
                    return None
                info = data[0]
                return {
                    "title": f"Play {info.get('name', 'Unknown Game')} Today!",
                    "creator": info.get("creator", {}).get("name", "Unknown"),
                    "description": info.get("description", ""),
                    "created": info.get("created", ""),
                    "thumbnail_url": f"https://www.roblox.com/asset-thumbnail/image?assetId={info.get('id')}&width=420&height=420&format=png"
                }
        except Exception as e:
            print(f"Error fetching game info: {e}")
            return None

    async def get_ugc_info(self, link: str):
        """Fetch Roblox UGC info by link"""
        try:
            item_id = int(link.rstrip("/").split("/catalog/")[1].split("/")[0])
        except Exception:
            return None
        url = f"https://catalog.roblox.com/v1/catalog/items/details?itemIds={item_id}"
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                item = data.get("data", [{}])[0]
                return {
                    "title": item.get("name", "UGC Item"),
                    "creator": item.get("creator", {}).get("name", "Unknown"),
                    "description": item.get("description", ""),
                    "thumbnail_url": item.get("productImages", [{}])[0].get("targetId", "")
                }
        except Exception as e:
            print(f"Error fetching UGC info: {e}")
            return None

    async def get_group_info(self, link: str):
        """Fetch Roblox group info by link"""
        try:
            group_id = int(link.rstrip("/").split("/groups/")[1].split("/")[0])
        except Exception:
            return None
        url = f"https://groups.roblox.com/v1/groups/{group_id}"
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                info = await resp.json()
                return {
                    "title": info.get("name", "Roblox Group"),
                    "creator": info.get("owner", {}).get("username", "Unknown"),
                    "description": info.get("description", ""),
                    "thumbnail_url": f"https://www.roblox.com/Thumbs/Group.ashx?gid={group_id}&x=420&y=420"
                }
        except Exception as e:
            print(f"Error fetching group info: {e}")
            return None

    # ===== Session cleanup =====
    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def __del__(self):
        if hasattr(self, 'session') and self.session and not self.session.closed:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.session.close())
            except:
                pass
