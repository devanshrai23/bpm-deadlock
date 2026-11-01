"""Takes screenshots of every app step (used for the report).
Start the app first (streamlit run app.py), then:  python tools/screenshots.py results/screens
"""
import sys
import time
from playwright.sync_api import sync_playwright

STEPS = [("1 · Process model", "1_model"), ("2 · Petri net", "2_petri"), ("3 · Detect deadlocks", "3_detect"),
         ("4 · Cause & fix", "4_fix"), ("5 · Token game", "5_token"), ("6 · Simulation", "6_sim"),
         ("All models · results", "7_all")]

out = sys.argv[1]
model = sys.argv[2] if len(sys.argv) > 2 else None
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1500, "height": 1000})
    pg.goto("http://localhost:8501")
    pg.wait_for_selector("text=Model source", timeout=60000)
    time.sleep(3)
    if model:
        pg.locator("[data-testid='stSelectbox']").first.click()
        time.sleep(1)
        pg.get_by_role("option", name=model).click()
        time.sleep(3)
    for label, fn in STEPS:
        pg.get_by_text(label, exact=True).click()
        time.sleep(5)
        pg.screenshot(path=f"{out}/{fn}{'_' + model if model else ''}.png", full_page=True)
        print("saved", fn)
    b.close()
