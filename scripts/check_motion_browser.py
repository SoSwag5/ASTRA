"""Read-only native-browser regression against an already running fictional preview.

Requires Python Playwright with Chromium installed. Pass --url explicitly;
this script never starts a server, scan, Gmail operation or write request.
"""
import argparse
import json
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Loopback ASTRA preview using fictional data only')
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        parser.error('Use a loopback fictional preview')
    checks, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, theme in [(1440, 'light'), (1440, 'dark'), (390, 'light'), (390, 'dark')]:
            context = browser.new_context(viewport={'width': width, 'height': 1000}, reduced_motion='no-preference')
            context.add_init_script("localStorage.setItem('welcomeDismissed','1');localStorage.setItem('themeChoice'," + json.dumps(theme) + ")")
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(args.url)
            page.locator('.campaign-heading').wait_for()
            for gap in [25, 80, 120, 200]:
                page.locator('aside').get_by_title('Today', exact=True).click()
                page.wait_for_timeout(500)
                boxes = [page.locator('aside').get_by_title(name, exact=True).bounding_box() for name in ('Progress', 'Jobs')]
                # Two genuine pointer clicks. Locator.click waits for stability,
                # and a third click can conceal a dropped second click.
                for index, box in enumerate(boxes):
                    if index:
                        page.wait_for_timeout(gap)
                    page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                page.wait_for_timeout(550)
                label = f'{width}/{theme}/{gap}ms'
                assert page.title() == 'Jobs · ASTRA', label + ': latest destination lost'
                assert page.locator('#workspace-main h1').evaluate('(el) => el === document.activeElement'), label + ': latest focus lost'
                assert page.locator('html').get_attribute('data-vt') is None, label + ': stale transition'
                checks.append(label)
            page.locator('aside').get_by_title('Settings', exact=True).click()
            page.wait_for_timeout(500)
            if width <= 1000:
                page.locator('.settings-select select').select_option('appearance')
            else:
                page.get_by_role('navigation', name='Settings sections').get_by_role('button', name='Appearance', exact=True).click()
            page.wait_for_timeout(500)
            choice = 'dark' if theme == 'light' else 'light'
            radio = page.locator(f'input[name=theme][value={choice}]')
            radio.check()
            assert radio.is_checked(), 'theme selection must acknowledge immediately'
            assert page.locator('html').get_attribute('data-theme') == choice, 'theme applied'
            assert page.evaluate("localStorage.getItem('themeChoice')") == choice, 'theme preference saved'
            checks.append(f'{width}/{theme}/immediate-theme')
            context.close()
        browser.close()
    assert not errors, errors
    print(json.dumps({'result': 'PASS', 'scenarios': len(checks), 'assertions': len(checks) * 3, 'checks': checks, 'page_errors': errors}, indent=2))


if __name__ == '__main__':
    main()
