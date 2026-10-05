var FOLDER_NAME = 'sheetparser-poc';
var DEFAULT_FONT = 'Malgun Gothic';

function out_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    var key = PropertiesService.getScriptProperties().getProperty('API_KEY');
    if (!key || body.key !== key) return out_({ok: false, error: 'unauthorized'});
    if (body.action === 'create') return out_(create_(body.spec, body.title));
    if (body.action === 'pdf') return out_(pdf_(body));
    if (body.action === 'delete') return out_(delete_(body.id));
    if (body.action === 'list') return out_(list_());
    return out_({ok: false, error: 'unknown action'});
  } catch (err) {
    return out_({ok: false, error: String(err), stack: err && err.stack});
  }
}

function doGet() { return out_({ok: true, msg: 'sheetparser-writer'}); }

function folder_() {
  var it = DriveApp.getFoldersByName(FOLDER_NAME);
  return it.hasNext() ? it.next() : DriveApp.createFolder(FOLDER_NAME);
}

function hexToColor_(hex) {
  var m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return null;
  var n = parseInt(m[1], 16);
  return {red: ((n >> 16) & 255) / 255, green: ((n >> 8) & 255) / 255, blue: (n & 255) / 255};
}

function border_(style) {
  if (!style || style === 'NONE') return {style: 'NONE'};
  return {style: style, color: {red: 0, green: 0, blue: 0}};
}

function create_(spec, title) {
  var R = spec.rows.length, C = spec.columns.length;
  var ss = SpreadsheetApp.create(title || ('sheetparser ' + new Date().toISOString()));
  var id = ss.getId();
  DriveApp.getFileById(id).moveTo(folder_());
  var sh = ss.getSheets()[0];
  var gid = sh.getSheetId();

  // 시트 크기를 표에 맞춘다 (남는 행/열 삭제, 부족하면 추가)
  if (sh.getMaxRows() < R) sh.insertRowsAfter(sh.getMaxRows(), R - sh.getMaxRows());
  if (sh.getMaxColumns() < C) sh.insertColumnsAfter(sh.getMaxColumns(), C - sh.getMaxColumns());
  if (sh.getMaxRows() > R) sh.deleteRows(R + 1, sh.getMaxRows() - R);
  if (sh.getMaxColumns() > C) sh.deleteColumns(C + 1, sh.getMaxColumns() - C);

  var reqs = [];
  // 기본 서식: 글꼴, 줄바꿈 CLIP(행 높이가 늘지 않게), 세로 가운데
  reqs.push({repeatCell: {
    range: {sheetId: gid, startRowIndex: 0, endRowIndex: R, startColumnIndex: 0, endColumnIndex: C},
    cell: {userEnteredFormat: {
      textFormat: {fontFamily: DEFAULT_FONT, fontSize: 10},
      wrapStrategy: 'CLIP', verticalAlignment: 'MIDDLE',
      padding: {top: 0, bottom: 0, left: 2, right: 2}}},
    fields: 'userEnteredFormat(textFormat,wrapStrategy,verticalAlignment,padding)'}});
  reqs.push({updateSheetProperties: {
    properties: {sheetId: gid, gridProperties: {hideGridlines: true}},
    fields: 'gridProperties.hideGridlines'}});
  spec.columns.forEach(function (w, i) {
    reqs.push({updateDimensionProperties: {
      range: {sheetId: gid, dimension: 'COLUMNS', startIndex: i, endIndex: i + 1},
      properties: {pixelSize: w}, fields: 'pixelSize'}});
  });
  spec.rows.forEach(function (h, i) {
    reqs.push({updateDimensionProperties: {
      range: {sheetId: gid, dimension: 'ROWS', startIndex: i, endIndex: i + 1},
      properties: {pixelSize: h}, fields: 'pixelSize'}});
  });

  // 셀 값/서식, 병합
  (spec.cells || []).forEach(function (c) {
    var rs = c.rs || 1, cs = c.cs || 1;
    var fmt = {};
    var fields = [];
    if (c.h) { fmt.horizontalAlignment = c.h; fields.push('horizontalAlignment'); }
    if (c.v) { fmt.verticalAlignment = c.v; fields.push('verticalAlignment'); }
    if (c.wrap !== undefined) { fmt.wrapStrategy = c.wrap ? 'WRAP' : (c.role === 'text' ? 'OVERFLOW_CELL' : 'CLIP'); fields.push('wrapStrategy'); }
    var tf = {fontFamily: c.font || DEFAULT_FONT}; fields.push('textFormat.fontFamily');
    if (c.size_pt) { tf.fontSize = Math.max(1, Math.round(c.size_pt)); fields.push('textFormat.fontSize'); }
    if (c.bold !== undefined) { tf.bold = !!c.bold; fields.push('textFormat.bold'); }
    if (c.underline !== undefined) { tf.underline = !!c.underline; fields.push('textFormat.underline'); }
    if (c.italic !== undefined) { tf.italic = !!c.italic; fields.push('textFormat.italic'); }
    var fg = hexToColor_(c.color);
    if (fg) { tf.foregroundColor = fg; fields.push('textFormat.foregroundColor'); }
    fmt.textFormat = tf;
    if (c.role === 'text') {  // v2 표 밖 텍스트: 여백 0, 넘치면 옆 칸으로
      fmt.padding = {top: 0, bottom: 0, left: 0, right: 0}; fields.push('padding');
      if (!c.wrap) fmt.wrapStrategy = 'OVERFLOW_CELL';
    }
    var bg = hexToColor_(c.bg);
    if (bg) { fmt.backgroundColor = bg; fields.push('backgroundColor'); }
    var cell = {userEnteredFormat: fmt};
    if (c.text !== undefined && c.text !== null && c.text !== '') {
      cell.userEnteredValue = {stringValue: String(c.text)}; // 문자열로 고정, 숫자 변환 방지
    }
    var f = fields.map(function (x) { return 'userEnteredFormat.' + x; });
    if (cell.userEnteredValue) f.push('userEnteredValue');
    reqs.push({updateCells: {
      rows: [{values: [cell]}],
      start: {sheetId: gid, rowIndex: c.r, columnIndex: c.c},
      fields: f.join(',')}});
    if (rs > 1 || cs > 1) {
      reqs.push({mergeCells: {
        range: {sheetId: gid, startRowIndex: c.r, endRowIndex: c.r + rs, startColumnIndex: c.c, endColumnIndex: c.c + cs},
        mergeType: 'MERGE_ALL'}});
    }
  });

  // 테두리: h[i][c] = 행 i 위쪽(i=0..R), v[r][j] = 열 j 왼쪽(j=0..C)
  var b = spec.borders || {};
  (b.h || []).forEach(function (row, i) {
    row.forEach(function (st, c) {
      if (!st || st === 'NONE') return;
      var o = {range: {sheetId: gid, startRowIndex: Math.min(i, R - 1), endRowIndex: Math.min(i, R - 1) + 1, startColumnIndex: c, endColumnIndex: c + 1}};
      o[i === R ? 'bottom' : 'top'] = border_(st);
      reqs.push({updateBorders: o});
    });
  });
  (b.v || []).forEach(function (row, r) {
    row.forEach(function (st, j) {
      if (!st || st === 'NONE') return;
      var o = {range: {sheetId: gid, startRowIndex: r, endRowIndex: r + 1, startColumnIndex: Math.min(j, C - 1), endColumnIndex: Math.min(j, C - 1) + 1}};
      o[j === C ? 'right' : 'left'] = border_(st);
      reqs.push({updateBorders: o});
    });
  });

  Sheets.Spreadsheets.batchUpdate({requests: reqs}, id);
  SpreadsheetApp.flush();
  // 행 높이가 내용 때문에 늘지 않도록 강제 지정
  spec.rows.forEach(function (h, i) { sh.setRowHeightsForced(i + 1, 1, h); });
  SpreadsheetApp.flush();
  // v2: 격자 위에 떠 있는 이미지 (서명 등)
  var nimg = 0;
  (spec.images || []).forEach(function (im) {
    var blob = Utilities.newBlob(Utilities.base64Decode(im.png_b64), 'image/png', 'img' + nimg + '.png');
    var img = sh.insertImage(blob, im.c + 1, im.r + 1, Math.round(im.dx_px || 0), Math.round(im.dy_px || 0));
    if (im.w_px && im.h_px) { img.setWidth(Math.round(im.w_px)); img.setHeight(Math.round(im.h_px)); }
    nimg++;
  });
  SpreadsheetApp.flush();
  return {ok: true, id: id, gid: gid, url: ss.getUrl(), nreq: reqs.length, nimg: nimg};
}

function pdf_(p) {
  var m = p.margins_in || {top: 0, bottom: 0, left: 0, right: 0};
  var url = 'https://docs.google.com/spreadsheets/d/' + p.id + '/export?format=pdf'
    + '&gid=' + p.gid + '&size=a4&portrait=true&scale=1&gridlines=false'
    + '&printtitle=false&sheetnames=false&pagenumbers=false&fzr=false&fzc=false'
    + '&top_margin=' + m.top + '&bottom_margin=' + m.bottom
    + '&left_margin=' + m.left + '&right_margin=' + m.right
    + '&horizontal_alignment=LEFT&vertical_alignment=TOP';
  var r = UrlFetchApp.fetch(url, {headers: {Authorization: 'Bearer ' + ScriptApp.getOAuthToken()}, muteHttpExceptions: true});
  if (r.getResponseCode() !== 200) return {ok: false, error: 'export ' + r.getResponseCode(), body: r.getContentText().slice(0, 300)};
  return {ok: true, pdf_b64: Utilities.base64Encode(r.getBlob().getBytes()), margins_in: m, scale: 1, size: 'a4', portrait: true};
}

function delete_(id) {
  DriveApp.getFileById(id).setTrashed(true);
  return {ok: true};
}

// sheetparser-poc 폴더의 파일 목록 (id, 이름, 생성시각). 고아/디버그 시트 정리용.
function list_() {
  var it = folder_().getFiles(), files = [];
  while (it.hasNext()) {
    var f = it.next();
    files.push({id: f.getId(), name: f.getName(), created: f.getDateCreated().toISOString(), url: f.getUrl()});
  }
  files.sort(function (a, b) { return a.created < b.created ? -1 : 1; });
  return {ok: true, count: files.length, files: files};
}
