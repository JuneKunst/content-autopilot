from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    gemini_api_key: str = ""
    claude_api_key: str = ""
    deepseek_api_key: str = ""
    ghost_url: str = "http://localhost:2368"
    ghost_admin_key: str = ""
    ghost_content_key: str = ""
    tg_bot_token: str = ""
    tg_channel_id: str = ""
    discord_webhook_url: str = ""
    db_url: str = "postgresql+asyncpg://autopilot:autopilot@localhost:5432/content_autopilot"
    dashboard_password: str = "admin"
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    github_token: str = ""
    youtube_api_key: str = ""
    mastodon_access_token: str = ""
    mastodon_instance: str = "https://mastodon.social"
    bluesky_identifier: str = ""
    bluesky_app_password: str = ""
    wp_site_url: str = ""
    wp_username: str = ""
    wp_app_password: str = ""
    naver_id: str = ""
    naver_password: str = ""
    naver_blog_id: str = ""
    tistory_email: str = ""
    tistory_password: str = ""
    tistory_blog_name: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
