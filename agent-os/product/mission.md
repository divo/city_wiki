# Product Mission

## Pitch

CityWandr is a mobile city guide app that helps travelers discover and explore cities through curated points of interest, powered by an automated dataset creation pipeline that eliminates the need for a team of editors while maintaining consistent quality and style across all content.

## Users

### Primary Customers

- **Travelers**: People exploring new cities who want reliable, well-organized recommendations for things to see, eat, drink, shop, and do
- **City Explorers**: Locals and visitors looking for curated lists and hidden gems beyond typical tourist guides

### User Personas

**The Weekend Explorer** (25-45)
- **Role:** Professional traveler, takes 3-5 city trips per year
- **Context:** Limited time in each city, wants to maximize experience
- **Pain Points:** Overwhelming options, inconsistent quality of travel content, outdated information
- **Goals:** Quickly find the best spots, discover local favorites, navigate efficiently

**The Spontaneous Wanderer** (20-35)
- **Role:** Flexible traveler who enjoys serendipitous discoveries
- **Context:** Prefers walking and exploring neighborhoods organically
- **Pain Points:** Generic "top 10" lists, lack of neighborhood-specific recommendations
- **Goals:** Find interesting spots nearby, understand district character, stumble upon quality experiences

## The Problem

### Content Curation at Scale

Traditional travel guides require teams of editors to research, write, and maintain content for each city. This is expensive, slow to update, and difficult to scale. WikiVoyage and similar sources provide raw data but lack consistent quality, style, and organization.

**Our Solution:** An automated pipeline that transforms sparse seed data into polished, consistent travel content using LLMs, geocoding services, and intelligent data enrichment - enabling one developer to maintain guides for hundreds of cities.

### Information Overload

Travelers face thousands of POI options with inconsistent descriptions, missing details, and no clear way to prioritize. Reviews are subjective and overwhelming.

**Our Solution:** AI-curated lists organized by theme, neighborhood, and category, with consistent description quality that helps users quickly understand what makes each place special.

## Differentiators

### Automated Quality at Scale

Unlike traditional travel guides that require editorial teams, CityWandr uses an automated pipeline to fetch, enrich, and rewrite content. This means faster updates, broader city coverage, and consistent quality without the overhead.

### Intelligent Data Enrichment

Unlike raw WikiVoyage data, CityWandr automatically geocodes addresses, deduplicates entries, matches OSM IDs for accuracy, and uses LLMs to rewrite descriptions in a consistent, engaging style. The result is clean, reliable data.

### Curated Without Curation Teams

Unlike apps that rely on user reviews or paid placements, CityWandr uses AI to generate themed lists (e.g., "Historic Architecture", "Late Night Eats") from quality-verified POI data, providing editorial-quality curation at zero marginal cost.

## Key Features

### Core Features (Mobile App)

- **City Guides:** Comprehensive POI listings organized by category (see, eat, drink, shop, sleep, play) and district
- **Curated Lists:** AI-generated themed collections of POIs for specific interests or experiences
- **Map Integration:** All POIs with verified coordinates for easy navigation
- **Offline Access:** Downloaded city data for use without connectivity

### Dataset Creation Features (This Codebase)

- **WikiVoyage Import:** Automated scraping and parsing of city data from WikiVoyage
- **Geocoding Pipeline:** Address-to-coordinates and coordinates-to-address resolution via Mapbox
- **Duplicate Detection:** Intelligent matching to identify and merge duplicate POIs
- **OSM Matching:** Local PBF file processing to match POIs with OpenStreetMap IDs
- **LLM Rewriting:** Consistent style and quality across all descriptions using OpenAI
- **List Generation:** AI-powered creation of themed POI collections
- **Web Console:** Review interface for data validation and manual refinement

### Advanced Features (Planned)

- **Seed-to-Guide Pipeline:** Start from just GPS coordinates, automatically build complete city guide
- **Hero Image Selection:** Automated fetching and ranking of city/POI images
- **Full Automation:** End-to-end pipeline requiring zero manual intervention
