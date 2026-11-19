(function () {
  "use strict";

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var show = function (el) { if (el) el.classList.remove("hidden"); };
  var hide = function (el) { if (el) el.classList.add("hidden"); };

  async function apiPost(url, data) {
    var res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      var msg = "请求失败（" + res.status + "），请稍后重试";
      try {
        var j = await res.json();
        if (j.detail) msg = j.detail;
        else if (j.message) msg = j.message;
      } catch (e) { /* 忽略非 JSON 响应 */ }
      throw new Error(msg);
    }
    return res;
  }

  async function streamSSE(res, onEvent) {
    if (!res.body) throw new Error("当前浏览器不支持流式输出，请更换浏览器");
    var reader = res.body.getReader();
    var decoder = new TextDecoder("utf-8");
    var buffer = "";
    var handle = function (block) {
      var line = block.split("\n").find(function (l) { return l.indexOf("data:") === 0; });
      if (!line) return;
      try {
        onEvent(JSON.parse(line.slice(5).trim()));
      } catch (e) { /* 忽略解析失败的片段 */ }
    };
    while (true) {
      var step = await reader.read();
      if (step.done) break;
      buffer += decoder.decode(step.value, { stream: true });
      var idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        handle(buffer.slice(0, idx).trim());
        buffer = buffer.slice(idx + 2);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) handle(buffer.trim());
  }

  /* ---------------- 写汇报：生成 ---------------- */
  var genForm = $("#gen-form");
  if (genForm) {
    var genBtn = $("#gen-btn");
    var genStatus = $("#gen-status");
    var streamBox = $("#stream-box");
    var streamText = $("#stream-text");
    var emptyState = $("#empty-state");
    var periodInput = $("#period");
    var typeSelect = genForm.querySelector('[name="report_type"]');

    var defaults = {};
    var defaultsEl = $("#period-defaults");
    if (defaultsEl) {
      try { defaults = JSON.parse(defaultsEl.textContent || "{}"); } catch (e) { defaults = {}; }
    }
    var prevType = typeSelect ? typeSelect.value : "";
    if (typeSelect && periodInput) {
      typeSelect.addEventListener("change", function () {
        var current = periodInput.value.trim();
        if (!current || current === defaults[prevType]) {
          periodInput.value = defaults[typeSelect.value] || "";
        }
        prevType = typeSelect.value;
      });
    }

    genForm.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      if (genBtn.disabled) return;
      var brief = (genForm.brief.value || "").trim();
      if (!brief) {
        genStatus.className = "status err";
        genStatus.textContent = "请先粘贴你的工作碎片";
        genForm.brief.focus();
        return;
      }

      genBtn.disabled = true;
      genStatus.className = "status";
      genStatus.textContent = "正在梳理你的工作碎片，整理成汇报…";
      hide(emptyState);
      show(streamBox);
      streamText.textContent = "";
      streamBox.scrollIntoView({ behavior: "smooth", block: "start" });

      try {
        var res = await apiPost("/api/generate", {
          brief: brief,
          position: genForm.position.value,
          report_type: genForm.report_type.value,
          audience: genForm.audience.value,
          length_key: genForm.length_key.value,
          period: periodInput ? periodInput.value : "",
          extra: genForm.extra.value
        });
        await streamSSE(res, function (data) {
          if (data.type === "chunk") {
            streamText.textContent += data.text;
          } else if (data.type === "error") {
            genStatus.className = "status err";
            genStatus.textContent = data.message;
          } else if (data.type === "done") {
            genStatus.className = "status ok";
            genStatus.textContent = "生成完成，剩余 " + data.remaining + " 次，正在打开…";
            window.location.href = "/reports/" + data.report_id;
          }
        });
      } catch (err) {
        genStatus.className = "status err";
        genStatus.textContent = err.message;
      } finally {
        genBtn.disabled = false;
      }
    });
  }

  /* ---------------- 报告详情：微调 ---------------- */
  var refineForm = $("#refine-form");
  if (refineForm) {
    var refineBtn = $("#refine-btn");
    var refineStatus = $("#refine-status");
    var refineBox = $("#stream-box");
    var refineText = $("#stream-text");
    var reportBody = $("#report-body");

    refineForm.querySelectorAll("[data-fill]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        refineForm.instruction.value = btn.getAttribute("data-fill") || "";
        refineForm.instruction.focus();
      });
    });

    refineForm.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var instruction = (refineForm.instruction.value || "").trim();
      if (!instruction) {
        refineStatus.className = "status err";
        refineStatus.textContent = "先写一句修改要求，或点上面的快捷指令";
        return;
      }

      refineBtn.disabled = true;
      refineStatus.className = "status";
      refineStatus.textContent = "正在按你的要求修改…";
      hide(reportBody);
      show(refineBox);
      refineText.textContent = "";
      refineBox.scrollIntoView({ behavior: "smooth", block: "start" });

      var failed = false;
      try {
        var res = await apiPost("/api/refine/" + refineForm.getAttribute("data-report-id"), {
          instruction: instruction,
          position: refineForm.position.value,
          report_type: refineForm.report_type.value
        });
        await streamSSE(res, function (data) {
          if (data.type === "chunk") {
            refineText.textContent += data.text;
          } else if (data.type === "error") {
            failed = true;
            refineStatus.className = "status err";
            refineStatus.textContent = data.message;
          } else if (data.type === "done") {
            refineStatus.className = "status ok";
            refineStatus.textContent = "修改完成，正在刷新…";
            window.location.reload();
          }
        });
      } catch (err) {
        failed = true;
        refineStatus.className = "status err";
        refineStatus.textContent = err.message;
      } finally {
        refineBtn.disabled = false;
        if (failed) {
          hide(refineBox);
          show(reportBody);
        }
      }
    });
  }

  /* ---------------- 购买：提交订单 ---------------- */
  var orderForm = $("#order-form");
  if (orderForm) {
    var orderBtn = $("#order-btn");
    var orderStatus = $("#order-status");
    var orderResult = $("#order-result");
    var orderNoEl = $("#order-no");
    var orderTip = $("#order-tip");
    var remarkInput = $("#order-remark");

    orderBtn.addEventListener("click", async function () {
      var picked = orderForm.querySelector('input[name="plan_id"]:checked');
      if (!picked) {
        orderStatus.className = "status err";
        orderStatus.textContent = "请先选择套餐";
        return;
      }
      var remark = (remarkInput.value || "").trim();
      if (!remark) {
        orderStatus.className = "status err";
        orderStatus.textContent = "请先填写付款备注或联系方式，方便客服核对";
        remarkInput.focus();
        return;
      }

      orderBtn.disabled = true;
      orderStatus.className = "status";
      orderStatus.textContent = "正在提交订单…";
      try {
        var res = await apiPost("/api/orders", { plan_id: picked.value, remark: remark });
        var data = await res.json();
        orderNoEl.textContent = data.order_no;
        var wechat = data.support_wechat || orderResult.getAttribute("data-wechat") || "";
        orderTip.textContent = wechat
          ? "把订单号和付款截图发微信 " + wechat + "，一般几分钟内处理完成"
          : (data.support_text || "把订单号和付款截图发给客服") + "，一般几分钟内处理完成";
        show(orderResult);
        orderStatus.className = "status ok";
        orderStatus.textContent = "订单已提交，客服核对到账后会自动发码";
        var queryInput = $("#query-no");
        if (queryInput) queryInput.value = data.order_no;
        orderResult.scrollIntoView({ behavior: "smooth", block: "center" });
      } catch (err) {
        orderStatus.className = "status err";
        orderStatus.textContent = err.message;
      } finally {
        orderBtn.disabled = false;
      }
    });
  }

  /* ---------------- 购买：查询订单 ---------------- */
  var queryForm = $("#query-form");
  if (queryForm) {
    var queryStatus = $("#query-status");
    var queryResult = $("#query-result");
    var queryInput = $("#query-no");

    queryForm.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var orderNo = (queryInput.value || "").trim();
      if (!orderNo) {
        queryStatus.className = "status err";
        queryStatus.textContent = "请先输入订单号";
        queryInput.focus();
        return;
      }

      queryStatus.className = "status";
      queryStatus.textContent = "正在查询…";
      hide(queryResult);
      try {
        var res = await fetch("/api/orders/" + encodeURIComponent(orderNo));
        if (!res.ok) {
          var errBody = {};
          try { errBody = await res.json(); } catch (e) { /* 忽略 */ }
          throw new Error(errBody.detail || "订单号不存在，请检查后重试");
        }
        var data = await res.json();
        $("#q-no").textContent = data.order_no;
        $("#q-plan").textContent = data.plan_name + " · " + data.uses + " 次";
        $("#q-amount").textContent = "¥" + data.amount;
        $("#q-status").textContent = data.status_text || data.status;
        var codeWrap = $("#q-code-wrap");
        var qTip = $("#q-tip");
        if (data.code) {
          $("#q-code").textContent = data.code;
          $("#q-activate").setAttribute("href", data.activate_url || ("/activate?code=" + encodeURIComponent(data.code)));
          show(codeWrap);
          qTip.textContent = "换设备时输入这个兑换码即可同步全部数据，请截图或复制保存。";
        } else {
          hide(codeWrap);
          qTip.textContent = "订单还在等待确认。若已付款，请把订单号和付款截图发给客服催单。";
        }
        show(queryResult);
        queryStatus.textContent = "";
      } catch (err) {
        queryStatus.className = "status err";
        queryStatus.textContent = err.message;
      }
    });
  }
})();
