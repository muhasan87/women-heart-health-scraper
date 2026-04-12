# Women's Heart Health Data Scraper

## Overview
common.py is the shared helper file used by all scrapers. It handles common tasks like requesting HTML, parsing pages with BeautifulSoup, cleaning text, extracting metadata, building the unified JSON record, and saving output files.

- scrape_abc.py is the source-specific scraper for ABC News.

- scrape_hra.py is the source-specific scraper for Heart Research Australia.

- scrape_mnt.py is the source-specific scraper for Medical News Today.


**Each scraper should try to collect a few relevant articles from its source, but for this stage we mainly need at least one clean JSON output per source.**
All JSON outputs should be saved in:

data/json/

The goal right now is to show:

-- multiple sources can be scraped
-- outputs are consistent
-- the system is modular and can scale to more sources later

NOTE:
Separate scraper files are normal because each website has different HTML structure, but the output format is unified across all sources.
