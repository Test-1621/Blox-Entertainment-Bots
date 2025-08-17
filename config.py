import os

class Config:
    """Configuration settings for the Discord verification bot"""
    
    # Discord Bot Token (from environment variable)
    DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    
    # Roblox API endpoints
    ROBLOX_USER_API = "https://users.roblox.com/v1/users/{user_id}"
    ROBLOX_USERNAME_API = "https://users.roblox.com/v1/usernames/users"
    
    # Verification settings
    CODE_LENGTH = 4
    CODE_EXPIRY_MINUTES = 10
    
    # File paths
    VERIFICATION_DATA_FILE = "data/verifications.json"
    
    # Bot settings
    COMMAND_PREFIX = "!"
    
    @classmethod
    def validate_config(cls):
        """Validate that required configuration is present"""
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_BOT_TOKEN environment variable is required")
        
        return True
