# LinkedIn Growth Helper

## Abstract
This repository presents an automated, safety-focused system for LinkedIn growth workflows. The project integrates data collection, scoring, and scheduled execution to support content discovery, engagement analysis, and structured notifications in a reproducible manner.

## Contributions
1. A modular architecture that separates scraping, analysis, execution, and notification responsibilities.
2. Configurable rate limiting and safety checks designed to reduce operational risk.
3. Repeatable deployment using both local scripts and containerized execution.

## System Overview
The system is composed of cooperating components:

- Scraper: session management, feed traversal, and filtering.
- Analyzer: profile and post scoring plus comment-generation heuristics.
- Executor: action execution with rate limiting.
- Notifier: Telegram notifications and offset tracking.
- Storage: schema-backed persistence and logs.

Entry points in the repository coordinate these components for scheduled runs and health checks.

## Repository Structure
- analyzer/ : scoring and content-generation logic.
- executor/ : action execution and rate limiting.
- scraper/ : LinkedIn session and feed access.
- notifier/ : Telegram bot integration.
- storage/ : database access, schema, and logs.
- config/ : configuration files (use settings.SAFE.yaml as a template).
- n8n/ : workflow definitions.

## Configuration
Create a local configuration file derived from the safe template:

1. Duplicate config/settings.SAFE.yaml to config/settings.yaml.
2. Populate credentials and operational parameters.
3. Keep config/settings.yaml out of version control.

## Installation
Local (Python):
1. Create and activate a virtual environment.
2. Install dependencies from requirements.txt.
3. Run via start.ps1 or start.bat.

Docker:
1. Review DOCKER_SETUP.md.
2. Build and run using docker-compose.yml.

## Usage
Primary entry points:
- main.py: orchestrates scrape, analyze, notify, and execute phases.
- scheduler.py: randomized scheduling for continuous operation.
- safety_check.py and health_check.py: operational checks.
- run_background.py and run_with_restart.py: alternative execution modes.

## Safety and Compliance
This project prioritizes safety with rate limits, approval gates, and session management. Users are responsible for ensuring that usage complies with LinkedIn terms of service and applicable law.

## Reproducibility
Reproducibility is supported through:
- deterministic configuration inputs,
- explicit schema definitions,
- containerized deployment options.

## Limitations
Browser automation can be brittle and is subject to platform changes. The system assumes careful human oversight and conservative operational parameters.

## Documentation
Detailed guides are provided in:
- SETUP_GUIDE.md
- DOCKER_SETUP.md
- QUICKSTART.md
- PRE_FLIGHT_CHECKLIST.md

## License
Add a license file to specify usage rights.

## Citation
If you use this repository in academic or technical work, cite it as:

LinkedIn Growth Helper. (2026). Automated LinkedIn growth workflows with safety constraints. GitHub repository.
