"""Exercise the forecast archive at a project subpath in Chromium."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import tempfile
import threading
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    screenshots = ROOT / "browser-checks"
    screenshots.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        shutil.copytree(ROOT / "dist", Path(temporary) / "example-tool")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=temporary))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/example-tool/")
                page.select_option("#provider", "noaa-gfs")
                page.wait_for_function("document.querySelector('#example').textContent.includes('airport measured')")
                page.locator("#example-link").click()
                page.wait_for_function("document.querySelector('#history-result').textContent.includes('airport measured')")
                page.wait_for_function("document.activeElement.id === 'valid-hour'")
                page.wait_for_selector("#rows tr")
                assert 38 <= page.locator("#rows tr").count() <= 40
                page.wait_for_selector("#hour-rows tr")
                page.locator("#valid-hour").select_option(index=1)
                page.wait_for_selector("#hour-rows tr")
                assert page.locator("#hour-rows a").first.get_attribute("href").startswith("./data/receipts/")
                page.select_option("#station", "halifax")
                page.wait_for_function("document.querySelector('#station-note').textContent.includes('8202251')")
                page.select_option("#day", "5")
                assert page.locator("#matched").inner_text().isdigit()
                page.select_option("#period", "Morning")
                page.select_option("#provider", "openweather")
                page.wait_for_function("document.querySelector('#receipt-info').textContent.includes('OpenWeather') || document.querySelector('#receipt-info').textContent.includes('no saved receipt')")
                page.select_option("#provider", "noaa-gfs")
                page.wait_for_selector("#rows tr")
                page.screenshot(path=str(screenshots / "desktop.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(screenshots / "mobile.png"), full_page=True)
                assert not errors, errors
                browser.close()
            print("Browser checks passed: project subpath, source, station, filters, receipts and mobile layout")
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
