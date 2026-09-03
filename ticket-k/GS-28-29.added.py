    # GS-28(TICKET-K):模型把整個陣列包成 JSON 字串 —— 兩個模型都會偶發,
    # 解得開就照常抽,不該因為多了一層引號就整批丟掉。
    box = sandbox_db()
    good_event = {
        "subject_id": "test.a", "event_type": "state_change", "value_after": "V2",
        "summary": "字串容器裡的好元素", "authority": "owner_decision",
        "impact": "low", "confidence": "high", "occurred_at": TS,
        "sources": [{"rowid": 9000, "quote": "引文"}],
    }
    wrapped = {
        "events": json.dumps([good_event], ensure_ascii=False),
        "subject_proposals": json.dumps(
            [{"proposed_key": "test.wrapped", "reason": "字串容器裡的提案"}],
            ensure_ascii=False),
    }
    try:
        ev28, pr28, dropped28, container28 = extractor.parse_response(
            box, wrapped, fixture_msgs, subjects, 0)
        ok28 = (len(ev28) == 1
                and ev28[0]["value_after"] == "V2"
                and len(pr28) == 1
                and pr28[0]["proposed_key"] == "test.wrapped"
                and dropped28 == 0
                and container28 == 0)
        detail28 = {"events": len(ev28), "proposals": len(pr28),
                    "dropped": dropped28, "container_drops": container28}
    except Exception as exc:  # noqa: BLE001
        ok28 = False
        detail28 = {"exception": f"{type(exc).__name__}: {exc}"}
    box.close()
    results["GS-28"] = {"title": "字串容器解得開就照常抽", "ok": ok28, **detail28}

    # GS-29(TICKET-K):容器是壞 JSON → 這批不可信,必須 failed 而不是 committed 0 events。
    # 9/2 一整天沒進檔案室,就是因為這種批被當成「今天沒事發生」。
    box = sandbox_db()
    dump_dir = os.path.join(
        os.path.dirname(extractor.HEALTH_FILE), "extract_dumps")
    dump_path = os.path.join(dump_dir, "batch_99001_events.txt")
    try:
        if os.path.exists(dump_path):
            os.remove(dump_path)
    except OSError:
        pass
    broken = {"events": '[{"summary": "斷在一半的 JSON", "sub'}
    try:
        box.execute(
            """INSERT INTO extraction_batches(batch_id,from_rowid,to_rowid,input_hash,
                   model,prompt_version,status,started_at)
               VALUES(99001,1,2,'hash','golden','golden','pending',?)""", (TS,))
        box.commit()
        ev29, pr29, dropped29, container29 = extractor.parse_response(
            box, broken, fixture_msgs, subjects, 99001)
        result29 = extractor.commit_batch(
            box, 99001, ev29, pr29, dropped29, container29, 1, 2, "hash")
        status29 = box.execute(
            "SELECT status FROM extraction_batches WHERE batch_id=99001").fetchone()[0]
        rows29 = box.execute(
            "SELECT COUNT(*) FROM events WHERE batch_id=99001").fetchone()[0]
        ok29 = (container29 > 0
                and status29 == "failed"
                and result29["ok"] is False
                and rows29 == 0
                and os.path.exists(dump_path))
        detail29 = {"container_drops": container29, "status": status29,
                    "events_written": rows29, "dump": os.path.exists(dump_path)}
    except Exception as exc:  # noqa: BLE001
        ok29 = False
        detail29 = {"exception": f"{type(exc).__name__}: {exc}"}
    box.close()
    try:
        os.remove(dump_path)
    except OSError:
        pass
    results["GS-29"] = {"title": "壞容器 → 批次 failed + 原文落檔", "ok": ok29, **detail29}
