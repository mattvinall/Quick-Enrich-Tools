from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://localhost:5432/quickenrich"
    redis_url: str = "redis://localhost:6379"
    jwt_secret: str = "change-me"
    jwt_expiry_hours: int = 24
    serper_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    resend_api_key: str = ""
    quickenrich_api_key: str = ""
    llm_provider: str = "gemini"
    storage_bucket: str = "quickenrich-results"
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    max_file_size_mb: int = 50
    max_rows: int = 100_000
    maps_max_per_search: int = 100  # upper bound per search term; Serper /maps returns up to 20 per page so we paginate
    maps_max_pages_per_search: int = 5  # safety cap on pagination depth (page 2+ is empirically empty on Serper /maps)
    maps_expand_to_nearby_cities: bool = True  # fan out each search to nearby cities parsed from initial result addresses
    maps_expansion_max_cities: int = 6  # cap on additional /maps calls per search (1 + N cities)
    funding_news_pages_per_query: int = 3  # pages of 100 news articles per funding query
    uploads_per_email_per_day: int = 50
    uploads_per_ip_per_day: int = 50
    downloads_per_job: int = 10
    serper_concurrency: int = 50
    verify_concurrency: int = 5
    normalize_concurrency: int = 50
    enrich_concurrency: int = 30
    pipeline_batch_size: int = 200
    llm_batch_size: int = 20
    normalize_batch_size: int = 200
    enrich_batch_size: int = 50
    scrape_do_api_key: str = ""
    scrape_concurrency: int = 30
    max_pages_per_site: int = 6
    scrape_timeout: int = 20
    intel_extraction_concurrency: int = 10
    cache_ttl_days: int = 7
    g2_scrape_concurrency: int = 5
    g2_max_pages_per_category: int = 500  # runaway-protection ceiling; 500 * 15/page = 7500 products, far beyond any real G2 category
    g2_max_total_companies: int = 50_000
    g2_cache_ttl_days: int = 3
    g2_serper_pages_per_query: int = 3  # pages of 100 organic results per G2 fallback query
    linkedin_search_concurrency: int = 50
    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
