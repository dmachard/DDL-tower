# RSS Feeds

DDLtower generates RSS 2.0 feeds to integrate with download clients, news readers, or automation scripts.

## Available Feeds

| Feed | Endpoint | Description |
| :--- | :--- | :--- |
| **RSS (Latest)** | `/api/rss` | All latest discovered releases |
| **RSS (Movies)** | `/api/rss/movies` | Latest movie releases |
| **RSS (Series)** | `/api/rss/series` | Latest series releases |
| **RSS (Downloads)** | `/api/rss/downloads` | Completed downloads history |

## Filtering Feeds

You can filter the main RSS feed (`/api/rss`) using URL query parameters:

- **Category**: Filter by media type:
  - `?category=movie`
  - `?category=series`
- **Search Query**: Filter by keywords:
  - `?q=search_term`

Example: `http://localhost:8001/api/rss?category=movie&q=avatar`
