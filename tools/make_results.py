"""runs/convert/*/convert.json -> 결과 표(마크다운) 출력. 사용: python3 tools/make_results.py"""
import glob, json, os
order = ["attendance_09", "activity_09", "meal_09", "sched_09", "sched_10", "sched_11", "sched_12", "form_activity", "form_attendance", "form_meal", "attendance_09_scan"]
rows = []
for n in order:
    p = "runs/convert/%s/convert.json" % n
    if not os.path.exists(p): continue
    c = json.load(open(p)); m = c["metrics"]
    ab = lambda d: "%.2f/%.2f" % (d["median"], d["max"]) if d else "-"
    line = (m.get("line_median_mm", m.get("median_mm")), m.get("line_max_mm", m.get("max_mm")))
    if c["kind"] == "pdf_vector":
        acc = "텍스트 일치 %.1f%%, 위치 찾음 %.0f%%" % (100 * m["text_ratio"], m["text_found_pct"])
        blk = ab(m.get("text_center_err_mm"))
        bold = "%.1f%% (원본 굵은 글줄 %d)" % (m["bold_match_pct"], m["bold_orig_count"])
    else:
        if "cell_acc" in c:
            acc = "셀 %d/%d (%.1f%%)" % (c["cells_ok"], c["cells_total"], c["cell_acc"])
        else:
            acc = "정답 없음, 글줄 찾음 %.0f%%" % m["text_found_pct"]
        blk = ab(m.get("block_center_err_mm")) if m.get("block_center_err_mm") else "-"
        bold = "%.1f%% (스펙 굵은 칸 %d)" % (m["bold_match_pct"], m["bold_spec_count"])
    rows.append("| %s | %s | %.0f | %s | %.2f / %.2f | %s | %s | %s | `%s` |" % (
        c["title"], c["kind"], c["sec_total"], acc, line[0], line[1], blk, bold,
        "(삭제됨)" if c["deleted"] else c["url"], c["side_png"].replace("_side.png", "_page_side.png") if c["kind"] != "pdf_vector" else c["side_png"]))
print("| 시트 제목 | 경로 | 시간(초) | 셀/텍스트 정확도 | 선 오차 중앙/최대(mm) | 블록 오차 중앙/최대(mm) | 굵기 일치 | 시트 URL | 나란히 PNG |")
print("|---|---|---|---|---|---|---|---|---|")
print("\n".join(rows))
