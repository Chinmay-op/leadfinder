import csv
import uuid
from models.business import Business
from models.icp import ICP

def _default_progress(msg: str):
    print(msg)

def run_linkedin_scraper(icp: ICP, state, test_mode: bool = False, on_company_found=None) -> list[Business]:
    """Thread-executor wrapper. Returns list of businesses."""
    state.progress("Starting LinkedIn scraper task (via Yahoo)...")
    
    import asyncio
    from main import run_main
    
    session_id = str(uuid.uuid4())
    businesses = []
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Use Yahoo/DDG scraper from main.py instead of Apify
        businesses = loop.run_until_complete(
            run_main(icp.search_keywords, icp.value_proposition, session_id=session_id, progress=state.progress, test_mode=test_mode, on_company_found=on_company_found)
        )
    except Exception as e:
        state.progress(f"Error in Yahoo scraper: {e}")
    finally:
        loop.close()
    
    return businesses
