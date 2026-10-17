// Run against a local pilot server: NODE_PATH=<playwright modules> node tests/browser_security.cjs
// API fixtures exercise browser behavior only; SQL/auth tests run in pytest/CI.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: chromium.executablePath() });
  try {
    const page = await browser.newPage();
    const errors = [];
    const requests = [];
    let frozen = false;
    let filmUrl = 'javascript:window.__unsafeLink = true';
    const id = '00000000-0000-0000-0000-000000000001';
    const payload = '<img src=x onerror="window.__xss=true">';
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      window.cspViolations = [];
      document.addEventListener('securitypolicyviolation', event => window.cspViolations.push(event.violatedDirective));
    });
    await page.route('**/api/v1/**', async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      requests.push([request.method(), path]);
      let body;
      if (path.endsWith('/vocab')) body = { groups: Object.fromEntries(['play_family', 'formation', 'motion', 'coverage_family', 'personnel'].map(key => [key, ['UNKNOWN', '2X2']])) };
      else if (path.endsWith('/play-searches')) body = request.method() === 'GET' ? { searches: [] } : { id };
      else if (path.endsWith('/plays')) body = { count: 1, total: 1, plays: [{ id, play_text: payload, offense_team_name: payload, defense_team_name: 'B', source_ids: [], tag_state: 'untagged', down: 1, distance: 10, quarter: 1, result_yards: 2 }] };
      else if (path.endsWith('/clip')) body = { film_url: filmUrl, provider: 'hudl', telestrate: { strokes: [] } };
      else if (path.endsWith('/call-sheet')) body = { week_plan: { status: frozen ? 'frozen' : 'open' }, rules: [], player_look_evidence: [] };
      else if (path.endsWith('/call-rules')) body = { rules: [{ id, status: 'candidate', rule_type: 'call', confidence: 'directional', situation: payload, call_name: 'Test', reason: payload, sample_n: 8 }] };
      else if (path.endsWith('/freeze')) { frozen = true; body = {}; }
      else body = {};
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.goto(process.env.PILOT_TEST_URL || 'http://127.0.0.1:8765/');
    await page.locator('#token').fill('x'.repeat(64));
    await page.locator('#planId').fill(id);
    await page.getByRole('button', { name: 'Use session', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#fFamily').options.length > 1);
    await page.getByRole('button', { name: 'Find plays', exact: true }).click();
    await page.locator('#playsBody button').waitFor();
    assert((await page.locator('#playsBody').innerText()).includes(payload));
    assert.equal(await page.locator('#playsBody img').count(), 0);
    await page.locator('#playsBody button').click();
    await page.locator('#clipDrawer.open').waitFor();
    assert.equal(await page.locator('#clipAttach a').count(), 0);
    await Promise.all([
      page.waitForResponse(response => response.url().endsWith('/tag-votes')),
      page.getByRole('button', { name: 'Vote', exact: true }).click(),
    ]);
    filmUrl = 'https://example.invalid/authorized-film';
    await page.getByRole('button', { name: 'Close', exact: true }).click();
    await page.locator('#playsBody button').click();
    const filmLink = page.getByRole('link', { name: 'Open in Hudl' });
    await filmLink.waitFor();
    assert.equal(await filmLink.getAttribute('href'), filmUrl);
    assert.equal(await filmLink.getAttribute('rel'), 'noopener noreferrer');
    await page.locator('.play-check').check();
    await page.getByRole('button', { name: 'Copy selected to Call-sheet' }).click();
    assert.equal(await page.locator('#ruleEvidence').inputValue(), id);
    await page.getByRole('button', { name: 'Refresh all', exact: true }).click();
    await page.getByRole('button', { name: 'Approve', exact: true }).waitFor();
    const patch = page.waitForResponse(response => response.request().method() === 'PATCH');
    await page.getByRole('button', { name: 'Approve', exact: true }).click();
    await patch;
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'Freeze Thursday sheet', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#freezeBtn').disabled);
    assert.equal(await page.locator('#editableArea').isVisible(), false);
    assert.deepEqual(errors, []);
    assert.deepEqual(await page.evaluate(() => window.cspViolations), []);
    assert.equal(await page.evaluate(() => Boolean(window.__xss || window.__unsafeLink)), false);
    // Probe the browser's actual CSP enforcement, beyond checking header strings.
    await page.evaluate(() => {
      const script = document.createElement('script');
      script.textContent = 'window.__inlineScriptExecuted = true';
      document.body.append(script);
      const button = document.createElement('button');
      button.setAttribute('onclick', 'window.__inlineHandlerExecuted = true');
      document.body.append(button);
      button.click();
    });
    await page.waitForFunction(() => window.cspViolations.length >= 2);
    assert.equal(await page.evaluate(() => Boolean(window.__inlineScriptExecuted || window.__inlineHandlerExecuted)), false);
    assert(requests.some(([method, path]) => method === 'POST' && path.endsWith('/tag-votes')));
    console.log('PASS: session, finder, escaped data, clip URLs, tag vote, call review, freeze, and enforced CSP.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
