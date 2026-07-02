/**
 * ResearchPulse subscription backend (Google Apps Script).
 *
 * Free, serverless backing for the signup page. It stores subscribers in a
 * Google Sheet and handles double opt-in confirmation + one-click unsubscribe.
 *
 * SETUP (one time, ~5 minutes):
 *   1. Create a Google Sheet. Add a header row:  email | topics | confirmed | token | created
 *   2. Extensions > Apps Script, paste this file.
 *   3. Set SHEET_ID below to your sheet's id (from its URL).
 *   4. Deploy > New deployment > type "Web app":
 *        - Execute as: Me
 *        - Who has access: Anyone
 *      Copy the web app URL. Put it in docs/index.html (APPS_SCRIPT_URL) and in
 *      the SITE_URL secret (so unsubscribe links point back here).
 *   5. File > Share > Publish to web > the sheet as CSV, and put that CSV URL in
 *      the SUBSCRIBERS_CSV_URL secret so the daily job can read confirmed rows.
 */

var SHEET_ID = 'PUT_YOUR_SHEET_ID_HERE';
var SHEET_NAME = 'Sheet1';
var NEWSLETTER_NAME = 'ResearchPulse';

function _sheet() {
  return SpreadsheetApp.openById(SHEET_ID).getSheetByName(SHEET_NAME);
}

function _token() {
  return Utilities.getUuid().replace(/-/g, '').substring(0, 24);
}

function _webAppUrl() {
  return ScriptApp.getService().getUrl();
}

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function _html(title, body) {
  var page =
    '<!doctype html><html><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<title>' + title + '</title>' +
    '<style>body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#0f172a;' +
    'color:#e2e8f0;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}' +
    '.card{background:#1e293b;padding:40px;border-radius:16px;max-width:460px;text-align:center;' +
    'box-shadow:0 10px 40px rgba(0,0,0,.4)}h1{color:#38bdf8;margin-top:0}a{color:#38bdf8}</style>' +
    '</head><body><div class="card"><h1>' + NEWSLETTER_NAME + '</h1>' + body +
    '</div></body></html>';
  return HtmlService.createHtmlOutput(page);
}

/** POST = subscribe. Accepts form-encoded fields: email, topics (csv). */
function doPost(e) {
  try {
    var email = (e.parameter.email || '').trim().toLowerCase();
    var topics = (e.parameter.topics || '').trim();
    if (!email || email.indexOf('@') < 0) {
      return _json({ ok: false, error: 'invalid_email' });
    }

    var sheet = _sheet();
    var data = sheet.getDataRange().getValues();
    for (var i = 1; i < data.length; i++) {
      if (String(data[i][0]).trim().toLowerCase() === email) {
        // Already present: refresh topics, keep confirmation state.
        sheet.getRange(i + 1, 2).setValue(topics);
        return _json({ ok: true, status: 'updated' });
      }
    }

    var token = _token();
    sheet.appendRow([email, topics, false, token, new Date()]);
    _sendConfirmation(email, token);
    return _json({ ok: true, status: 'pending_confirmation' });
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

/** GET = confirm or unsubscribe via tokenized links. */
function doGet(e) {
  var action = e.parameter.action || '';
  var token = (e.parameter.token || '').trim();
  if (!token) {
    return _html('Subscribe', '<p>Use the signup form to subscribe.</p>');
  }

  var sheet = _sheet();
  var data = sheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][3]).trim() === token) {
      if (action === 'confirm') {
        sheet.getRange(i + 1, 3).setValue(true);
        return _html('Confirmed',
          '<p>You are subscribed. Your first digest arrives tomorrow morning.</p>');
      }
      if (action === 'unsubscribe') {
        sheet.deleteRow(i + 1);
        return _html('Unsubscribed',
          '<p>You have been removed. Sorry to see you go!</p>');
      }
    }
  }
  return _html('Link expired', '<p>This link is no longer valid.</p>');
}

function _sendConfirmation(email, token) {
  var base = _webAppUrl();
  var confirmUrl = base + '?action=confirm&token=' + token;
  var subject = 'Confirm your ' + NEWSLETTER_NAME + ' subscription';
  var body =
    'Thanks for signing up for ' + NEWSLETTER_NAME + '!\n\n' +
    'Please confirm your subscription by clicking the link below:\n' +
    confirmUrl + '\n\n' +
    'If you did not request this, you can ignore this email.';
  MailApp.sendEmail(email, subject, body);
}
