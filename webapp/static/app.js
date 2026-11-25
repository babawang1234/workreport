(function () {
  "use strict";

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var show = function (el) { if (el) el.classList.remove("hidden"); };
  var hide = function (el) { if (el) el.classList.add("hidden"); };

  // 顶栏滚动到一定位置时加深分隔线
  var topbar = $(".topbar");
  if (topbar) {
    var onScroll = function () {
      topbar.classList.toggle("scrolled", window.scrollY > 8);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ---------------- 滚动动效：进度条 / 视差 / 错峰入场 / 数字滚动 ---------------- */
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var finePointer = window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  var raf = window.requestAnimationFrame || function (fn) { return setTimeout(fn, 16); };

  // 顶部阅读进度
  var progressBar = document.createElement("div");
  progressBar.className = "scroll-progress";
  document.body.appendChild(progressBar);

  // 首屏演示舞台与文案随滚动产生视差
  var heroStage = document.getElementById("hero-stage");
  var heroCopy = document.querySelector(".hero-main");
  var demoCardEl = document.getElementById("demo-card");
  var carouselRows = [];
  var scrollQueued = false;
  var updateScroll = function () {
    scrollQueued = false;
    var y = window.scrollY || 0;
    var max = document.documentElement.scrollHeight - window.innerHeight;
    var ratio = max > 0 ? Math.min(1, Math.max(0, y / max)) : 0;
    progressBar.style.transform = "scaleX(" + ratio.toFixed(4) + ")";
    if (reduce) return;
    if (heroStage) {
      heroStage.style.setProperty("--sy", (Math.min(y, 900) * 0.07).toFixed(1) + "px");
    }
    if (heroCopy) {
      var p = Math.min(1, y / 520);
      heroCopy.style.setProperty("--hy", (-p * 44).toFixed(1) + "px");
      heroCopy.style.setProperty("--hs", (1 - p * 0.015).toFixed(4));
      heroCopy.style.setProperty("--ho", (1 - p * 0.35).toFixed(3));
    }
    if (demoCardEl) {
      var q = Math.min(1, y / 620);
      demoCardEl.style.setProperty("--sx", (q * 7).toFixed(2));
      demoCardEl.style.setProperty("--ss", (1 - q * 0.05).toFixed(3));
    }
  };
  window.addEventListener("scroll", function () {
    if (!scrollQueued) { scrollQueued = true; raf(updateScroll); }
  }, { passive: true });
  window.addEventListener("resize", function () {
    carouselRows.forEach(function (row) { row.layout(); });
    updateScroll();
  });
  updateScroll();

  // 子元素错峰上浮（用 Web Animations，结束后不残留样式，避免影响 hover）
  var groupKids = function (group) {
    return Array.prototype.slice.call(group.children).filter(function (el) {
      return !el.classList.contains("hidden");
    });
  };
  var playGroup = function (group) {
    var deep = group.classList.contains("plan-grid");
    var from = deep ? "translateY(30px) scale(.94)" : "translateY(24px)";
    var to = deep ? "translateY(0) scale(1)" : "translateY(0)";
    groupKids(group).forEach(function (el, i) {
      if (el.style.opacity === "0") el.style.opacity = "";
      if (!el.animate) return;
      el.animate([
        { opacity: 0, transform: from },
        { opacity: 1, transform: to }
      ], {
        duration: 760,
        delay: i * 90,
        easing: "cubic-bezier(.22,.61,.36,1)",
        fill: "backwards"
      });
    });
  };
  var staggerGroups = document.querySelectorAll(
    ".hero-stats, .steps, .plan-grid, .faq, .pricing-foot, .value-list, .pay-grid"
  );
  if (staggerGroups.length && "IntersectionObserver" in window && !reduce) {
    staggerGroups.forEach(function (group) {
      groupKids(group).forEach(function (el) { el.style.opacity = "0"; });
      var gio = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            playGroup(entry.target);
            gio.disconnect();
          }
        });
      }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
      gio.observe(group);
    });
  }

  // 区块标题的下划线随滚动绘出
  var heads = document.querySelectorAll(".section-head");
  if (heads.length && "IntersectionObserver" in window) {
    var hio = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("seen");
          hio.unobserve(entry.target);
        }
      });
    }, { threshold: 0.35 });
    heads.forEach(function (el) { hio.observe(el); });
  } else {
    heads.forEach(function (el) { el.classList.add("seen"); });
  }

  // 首屏数字从 0 滚到目标值
  var counters = document.querySelectorAll("[data-count]");
  if (counters.length && "IntersectionObserver" in window && !reduce) {
    var countIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        countIO.unobserve(el);
        var target = parseFloat(el.getAttribute("data-count")) || 0;
        var suffix = el.getAttribute("data-suffix") || "";
        var start = null;
        var tick = function (ts) {
          if (start === null) start = ts;
          var p = Math.min(1, (ts - start) / 1000);
          var eased = 1 - Math.pow(1 - p, 3);
          el.textContent = Math.round(target * eased) + suffix;
          if (p < 1) raf(tick);
        };
        el.textContent = "0" + suffix;
        raf(tick);
      });
    }, { threshold: 0.6 });
    counters.forEach(function (el) { countIO.observe(el); });
  }

  // 首屏大标题：字与遮罩由服务端直接渲染，动画在首帧即开始，不依赖 JS
  var splitTitle = document.querySelector("[data-split]");

  // 首屏光晕跟随指针（只在精细指针 + 非减弱动效时启用）
  var heroEl = document.querySelector(".hero");
  var auraEl = document.getElementById("hero-aura");
  if (heroEl && auraEl && finePointer && !reduce) {
    heroEl.addEventListener("pointermove", function (ev) {
      var rect = heroEl.getBoundingClientRect();
      auraEl.style.setProperty("--mx", ((ev.clientX - rect.left) / rect.width * 100).toFixed(1) + "%");
      auraEl.style.setProperty("--my", ((ev.clientY - rect.top) / rect.height * 100).toFixed(1) + "%");
      auraEl.classList.add("on");
    }, { passive: true });
    heroEl.addEventListener("pointerleave", function () { auraEl.classList.remove("on"); });
  }

  // 大标题跟随指针做轻微 3D 转动
  if (heroEl && splitTitle && finePointer && !reduce) {
    var tiltFrame = 0;
    heroEl.addEventListener("pointermove", function (ev) {
      if (tiltFrame) return;
      tiltFrame = raf(function () {
        tiltFrame = 0;
        var rect = heroEl.getBoundingClientRect();
        var px = (ev.clientX - rect.left) / rect.width - 0.5;
        var py = (ev.clientY - rect.top) / rect.height - 0.5;
        splitTitle.style.transform =
          "perspective(1100px) rotateX(" + (-py * 7).toFixed(2) + "deg) rotateY(" + (px * 9).toFixed(2) + "deg)";
      });
    }, { passive: true });
    heroEl.addEventListener("pointerleave", function () { splitTitle.style.transform = ""; });
  }

  // 定价区光束跟随指针
  var pricingSec = document.getElementById("pricing");
  if (pricingSec && finePointer && !reduce) {
    pricingSec.addEventListener("pointermove", function (ev) {
      var rect = pricingSec.getBoundingClientRect();
      pricingSec.style.setProperty("--px", ((ev.clientX - rect.left) / rect.width * 100).toFixed(1) + "%");
      pricingSec.style.setProperty("--py", ((ev.clientY - rect.top) / rect.height * 100).toFixed(1) + "%");
    }, { passive: true });
  }

  // 区块滚动入场
  var revealEls = document.querySelectorAll(".reveal");
  if (revealEls.length) {
    if ("IntersectionObserver" in window && !reduce) {
      var revealIO = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            revealIO.unobserve(entry.target);
          }
        });
      }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
      revealEls.forEach(function (el) { revealIO.observe(el); });
    } else {
      revealEls.forEach(function (el) { el.classList.add("in"); });
    }
  }

  // 右侧章节导航：滚动到哪一段就点亮哪一项
  var railLinks = document.querySelectorAll(".scroll-rail a[data-rail]");
  if (railLinks.length && "IntersectionObserver" in window) {
    var railMap = {};
    railLinks.forEach(function (link) { railMap[link.getAttribute("data-rail")] = link; });
    var railIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var link = railMap[entry.target.id];
        if (link) link.classList.toggle("on", entry.isIntersecting);
      });
    }, { threshold: 0.25, rootMargin: "-20% 0px -40% 0px" });
    Object.keys(railMap).forEach(function (id) {
      var sec = document.getElementById(id);
      if (sec) railIO.observe(sec);
    });
  }

  // 套餐卡随指针轻微 3D 倾斜
  if (finePointer && !reduce) {
    document.querySelectorAll(".plan-card").forEach(function (card) {
      card.addEventListener("pointermove", function (ev) {
        var rect = card.getBoundingClientRect();
        var mx = ev.clientX - rect.left;
        var my = ev.clientY - rect.top;
        var px = mx / rect.width - 0.5;
        var py = my / rect.height - 0.5;
        card.classList.add("is-tilting");
        card.style.setProperty("--ty", (px * 6).toFixed(2) + "deg");
        card.style.setProperty("--tx", (-py * 5).toFixed(2) + "deg");
        card.style.setProperty("--mx", mx.toFixed(0) + "px");
        card.style.setProperty("--my", my.toFixed(0) + "px");
      }, { passive: true });
      card.addEventListener("pointerleave", function () {
        card.classList.remove("is-tilting");
        card.style.removeProperty("--tx");
        card.style.removeProperty("--ty");
      });
    });
  }

  // 购买页：选中套餐后高亮卡片，并同步订单摘要
  var planRadios = document.querySelectorAll('.plan-card input[type="radio"]');
  if (planRadios.length) {
    var orderBtn = document.getElementById("order-btn");
    var sumPlan = document.getElementById("sum-plan");
    var sumAmount = document.getElementById("sum-amount");
    var sumUses = document.getElementById("sum-uses");
    var syncPicked = function (animate) {
      planRadios.forEach(function (input) {
        var card = input.closest(".plan-card");
        if (!card) return;
        card.classList.toggle("picked", input.checked);
        if (!input.checked) return;
        var name = card.getAttribute("data-name") || "";
        var price = card.getAttribute("data-price") || "";
        var uses = card.getAttribute("data-uses") || "";
        if (sumPlan && name) sumPlan.textContent = name;
        if (sumAmount && price) sumAmount.textContent = "¥" + price;
        if (sumUses && uses) sumUses.textContent = uses + " 次";
        if (orderBtn && name) {
          orderBtn.textContent = "生成「" + name + "」订单并扫码";
          orderBtn.setAttribute("aria-label", "生成" + name + "订单，金额" + price);
        }
        if (animate && card.animate) {
          card.animate([
            { transform: "scale(1)" },
            { transform: "scale(1.015)" },
            { transform: "scale(1)" }
          ], { duration: 340, easing: "cubic-bezier(.22,1.35,.36,1)" });
        }
      });
    };
    planRadios.forEach(function (input) {
      input.addEventListener("change", function () { syncPicked(true); });
    });
    syncPicked(false);
  }

  // 购买页：支付宝 / 微信切换
  var payChannel = "alipay";
  var payTabs = document.querySelectorAll(".pay-tab");
  var payStages = document.querySelectorAll(".qr-stage");
  if (payTabs.length) {
    var setChannel = function (channel) {
      payChannel = channel === "wxpay" ? "wxpay" : "alipay";
      payTabs.forEach(function (tab) {
        var on = tab.getAttribute("data-channel") === payChannel;
        tab.classList.toggle("on", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
      });
      payStages.forEach(function (stage) {
        stage.classList.toggle("hidden", stage.getAttribute("data-stage") !== payChannel);
      });
      var sumChannel = document.getElementById("sum-channel");
      if (sumChannel) sumChannel.textContent = payChannel === "wxpay" ? "微信支付" : "支付宝";
      // 已有待付款订单时，让订单区跟着换渠道重新下单
      document.dispatchEvent(new CustomEvent("paychannelchange", { detail: payChannel }));
    };
    payTabs.forEach(function (tab) {
      tab.addEventListener("click", function () { setChannel(tab.getAttribute("data-channel")); });
    });
    setChannel("alipay");
  }

  /* ---------------- 点击翻页 + 自动轮播（首页三步 / 定价） ---------------- */
  var setupCarousel = function (sectionId, trackId, dotsId) {
    var section = document.getElementById(sectionId);
    var track = document.getElementById(trackId);
    if (!section || !track) return;
    var dots = document.getElementById(dotsId);
    var cards = track.children;
    var index = 0;
    var timer = null;
    var restartTimer = null;
    var PAGE_MS = 2000;

    var per = function () {
      return window.matchMedia("(min-width: 901px)").matches
        ? (parseInt(section.getAttribute("data-per"), 10) || 1)
        : 1;
    };
    var pages = function () { return Math.max(1, Math.ceil(cards.length / per())); };

    var buildDots = function () {
      if (!dots) return;
      var n = pages();
      if (dots.children.length === n) return;
      dots.innerHTML = "";
      for (var i = 0; i < n; i++) {
        var b = document.createElement("button");
        b.type = "button";
        b.setAttribute("data-page", String(i));
        b.setAttribute("aria-label", "第 " + (i + 1) + " 页");
        dots.appendChild(b);
      }
    };

    var apply = function () {
      if (!cards.length) return;
      var pp = per();
      track.style.setProperty("--per", pp);
      buildDots();
      if (index > pages() - 1) index = pages() - 1;
      var gap = parseFloat(window.getComputedStyle(track).columnGap) || 0;
      var cardW = cards[0].getBoundingClientRect().width + gap;
      track.style.setProperty("--shift", (-index * pp * cardW).toFixed(1) + "px");
      if (dots) {
        for (var i = 0; i < dots.children.length; i++) {
          var on = i === index;
          dots.children[i].classList.toggle("on", on);
          dots.children[i].setAttribute("aria-selected", on ? "true" : "false");
        }
      }
      for (var j = 0; j < cards.length; j++) {
        cards[j].classList.toggle("active", Math.floor(j / pp) === index);
      }
    };

    var go = function (target) {
      index = (target + pages()) % pages();
      apply();
    };

    var stop = function () {
      if (timer) { clearInterval(timer); timer = null; }
    };
    var start = function () {
      stop();
      if (reduce) return;
      timer = setInterval(function () { go(index + 1); }, PAGE_MS);
    };
    var pause = function () {
      stop();
      if (restartTimer) { clearTimeout(restartTimer); restartTimer = null; }
    };
    var resumeSoon = function (ms) {
      pause();
      restartTimer = setTimeout(start, ms || 9000);
    };

    section.querySelectorAll(".carousel-arrow").forEach(function (btn) {
      btn.addEventListener("click", function () {
        go(index + parseInt(btn.getAttribute("data-dir"), 10));
        resumeSoon(9000);
      });
    });

    if (dots) {
      dots.addEventListener("click", function (ev) {
        var btn = ev.target.closest("button[data-page]");
        if (!btn) return;
        go(parseInt(btn.getAttribute("data-page"), 10));
        resumeSoon(9000);
      });
    }

    section.addEventListener("pointerenter", pause);
    section.addEventListener("pointerleave", function () {
      if (!restartTimer) start();
    });
    section.addEventListener("focusin", pause);
    section.addEventListener("focusout", start);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) stop(); else start();
    });

    carouselRows.push({ layout: apply });
    apply();
    setTimeout(apply, 150);
    start();
  };

  setupCarousel("flow", "flow-track", "flow-dots");
  setupCarousel("pricing", "plan-track", "price-dots");

  // 右侧章节导航轨：跟随滚动高亮当前区块
  var railLinks = document.querySelectorAll(".scroll-rail a");
  if (railLinks.length && "IntersectionObserver" in window) {
    var railIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        railLinks.forEach(function (a) {
          a.classList.toggle("on", a.getAttribute("data-rail") === entry.target.id);
        });
      });
    }, { rootMargin: "-42% 0px -42% 0px", threshold: 0 });
    ["flow", "pricing", "activate", "faq"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) railIO.observe(el);
    });
  }

  // 元素进入视口时淡入
  var revealItems = document.querySelectorAll(".reveal");
  if (revealItems.length && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });
    revealItems.forEach(function (el) { io.observe(el); });
  } else {
    revealItems.forEach(function (el) { el.classList.add("in"); });
  }

  // 卡片上的鼠标跟随柔光
  var spotEls = document.querySelectorAll(".card, .step, .plan-card, .report-row, .faq details, .value-card");
  spotEls.forEach(function (el) {
    el.classList.add("spot");
    el.addEventListener("pointermove", function (ev) {
      var rect = el.getBoundingClientRect();
      el.style.setProperty("--mx", (ev.clientX - rect.left) + "px");
      el.style.setProperty("--my", (ev.clientY - rect.top) + "px");
    }, { passive: true });
  });

  // 首屏演示卡跟随鼠标轻微倾斜
  var stage = document.getElementById("hero-stage");
  if (stage) {
    var demo = stage.querySelector(".demo-card");
    var hero = stage.closest(".hero") || stage;
    if (demo) {
      hero.addEventListener("pointermove", function (ev) {
        var rect = stage.getBoundingClientRect();
        var px = (ev.clientX - rect.left) / rect.width - 0.5;
        var py = (ev.clientY - rect.top) / rect.height - 0.5;
        demo.style.setProperty("--ry", (-4 + px * 5).toFixed(2));
        demo.style.setProperty("--rx", (1 - py * 3.5).toFixed(2));
      }, { passive: true });
      hero.addEventListener("pointerleave", function () {
        demo.style.removeProperty("--ry");
        demo.style.removeProperty("--rx");
      });
    }
  }

  // 首屏演示：粘贴碎片 → 选岗位/类型 → 生成 → 四模块成稿 → 导出
  var demoCard = document.getElementById("demo-card");
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (demoCard && !reduceMotion) {
    var typed = document.getElementById("demo-typed");
    var demoBtn = document.getElementById("demo-btn");
    var demoLive = document.getElementById("demo-live");
    var demoDoc = document.getElementById("demo-doc");
    var demoProgress = document.getElementById("demo-progress");
    var demoPanel = document.getElementById("demo-panel");
    var cursor = document.getElementById("demo-cursor");
    var frags = document.getElementById("demo-frags");
    var pasteTag = document.getElementById("demo-paste");
    var posSel = document.getElementById("demo-position");
    var typeSel = document.getElementById("demo-type");
    var posText = document.getElementById("demo-position-text");
    var typeText = document.getElementById("demo-type-text");
    var docTitle = document.getElementById("demo-doc-title");
    var exportBtn = document.getElementById("demo-export");
    var toast = document.getElementById("demo-toast");
    var modules = demoDoc.querySelectorAll(".doc-module");
    var demoText = "登录页改版这周上线，转化率涨了 12%\n回归测试修掉 3 个阻塞问题\n下周做数据看板";
    var selects = [posSel, typeSel];

    var sleep = function (ms) {
      return new Promise(function (resolve) { setTimeout(resolve, ms); });
    };

    var moveTo = function (el, dx, dy) {
      var cardRect = demoCard.getBoundingClientRect();
      var rect = el.getBoundingClientRect();
      cursor.style.transform = "translate(" +
        (rect.left - cardRect.left + dx) + "px," +
        (rect.top - cardRect.top + dy) + "px)";
    };

    var closeSelect = function (sel) {
      sel.classList.remove("open", "selecting");
      sel.querySelectorAll("[data-option]").forEach(function (o) { o.classList.remove("pick"); });
    };

    var openSelect = function (sel, value) {
      sel.classList.add("open", "selecting");
      sel.querySelectorAll("[data-option]").forEach(function (o) {
        o.classList.toggle("pick", o.getAttribute("data-option") === value);
      });
    };

    var resetDemo = function () {
      demoCard.classList.add("js-demo");
      typed.textContent = "";
      modules.forEach(function (m) { m.classList.remove("show"); });
      demoProgress.classList.remove("on");
      demoBtn.classList.remove("loading", "pressed");
      demoBtn.textContent = "一键生成汇报";
      demoPanel.classList.remove("active", "flash");
      frags.classList.remove("run");
      pasteTag.classList.remove("on");
      posText.textContent = "运营";
      typeText.textContent = "日报";
      docTitle.textContent = "产品经理 · 周报";
      exportBtn.classList.remove("pressed", "done");
      exportBtn.textContent = "导出 Word";
      toast.classList.remove("show");
      selects.forEach(closeSelect);
      demoLive.className = "demo-live";
      demoLive.textContent = "AI 待命";
      cursor.classList.remove("show");
      cursor.style.transform = "translate(-40px, -40px)";
    };

    var typeBrief = async function () {
      for (var i = 0; i < demoText.length; i++) {
        typed.textContent += demoText[i];
        await sleep(demoText[i] === "\n" ? 180 : 24 + Math.random() * 22);
      }
    };

    var runDemo = async function () {
      resetDemo();
      await sleep(450);
      cursor.classList.add("show");
      moveTo(demoPanel, 54, 26);
      await sleep(550);

      frags.classList.add("run");
      demoPanel.classList.add("flash");
      await sleep(620);
      demoPanel.classList.remove("flash");
      demoPanel.classList.add("active");
      pasteTag.classList.add("on");
      demoLive.textContent = "已识别碎片";
      await typeBrief();
      await sleep(280);
      demoPanel.classList.remove("active");

      moveTo(posSel, 18, 6);
      await sleep(450);
      openSelect(posSel, "产品经理");
      await sleep(360);
      moveTo(posSel.querySelector('[data-option="产品经理"]'), 6, 4);
      await sleep(320);
      posText.textContent = "产品经理";
      closeSelect(posSel);
      await sleep(300);

      moveTo(typeSel, 18, 6);
      await sleep(430);
      openSelect(typeSel, "周报");
      await sleep(340);
      moveTo(typeSel.querySelector('[data-option="周报"]'), 6, 4);
      await sleep(300);
      typeText.textContent = "周报";
      closeSelect(typeSel);
      docTitle.textContent = "产品经理 · 周报";
      await sleep(360);

      moveTo(demoBtn, -4, 12);
      await sleep(500);
      demoBtn.classList.add("pressed");
      await sleep(150);
      demoBtn.classList.remove("pressed");

      demoBtn.classList.add("loading");
      demoBtn.textContent = "生成中…";
      demoLive.className = "demo-live busy";
      demoLive.textContent = "正在整理 4 个模块";
      demoProgress.classList.add("on");
      await sleep(900);

      for (var i = 0; i < modules.length; i++) {
        modules[i].classList.add("show");
        await sleep(320);
      }
      await sleep(320);
      demoLive.className = "demo-live done";
      demoLive.textContent = "已生成";
      demoBtn.classList.remove("loading");
      demoBtn.textContent = "一键生成汇报";
      cursor.classList.remove("show");

      await sleep(900);
      cursor.classList.add("show");
      moveTo(exportBtn, 4, 6);
      await sleep(520);
      exportBtn.classList.add("pressed");
      await sleep(140);
      exportBtn.classList.remove("pressed");
      exportBtn.classList.add("done");
      exportBtn.textContent = "已导出";
      toast.classList.add("show");
      await sleep(2600);

      runDemo();
    };

    runDemo();
  }

  // 三步区演示：进入视口或钉住切换时启动对应动画
  var stepEls = document.querySelectorAll(".step");
  if (stepEls.length && "IntersectionObserver" in window) {
    var stepIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) entry.target.classList.add("active");
      });
    }, { threshold: 0.35 });
    stepEls.forEach(function (el) { stepIO.observe(el); });
  } else {
    stepEls.forEach(function (el) { el.classList.add("active"); });
  }

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
    var trialExhausted = false;

    // 草稿自动保存 + 四段式框架，方便整周随手记录
    var briefEl = genForm.querySelector('[name="brief"]');
    var draftTip = $("#draft-tip");
    var draftKey = "workbrief.draft." + (genForm.getAttribute("data-code") || "guest");
    var draftTimer = null;
    if (briefEl) {
      try {
        var savedDraft = localStorage.getItem(draftKey);
        if (savedDraft && !briefEl.value.trim()) {
          briefEl.value = savedDraft;
          if (draftTip) draftTip.textContent = "已恢复上次未提交的草稿，可直接继续编辑。";
        }
      } catch (e) { /* 隐私模式忽略 */ }

      briefEl.addEventListener("input", function () {
        if (draftTimer) clearTimeout(draftTimer);
        draftTimer = setTimeout(function () {
          try {
            if (briefEl.value.trim()) localStorage.setItem(draftKey, briefEl.value);
            else localStorage.removeItem(draftKey);
            if (draftTip) draftTip.textContent = "草稿已自动保存到本机。";
          } catch (e) { /* 忽略 */ }
        }, 500);
      });
    }

    /* ---------- 导入素材：文档 / 截图 / 网页链接 ---------- */
    var extractFile = $("#extract-file");
    var extractUrl = $("#extract-url");
    var extractUrlBtn = $("#extract-url-btn");
    var extractStatus = $("#extract-status");
    var extractLimit = $("#extract-limit");

    var extractOptions = function () {
      return {
        limit: extractLimit ? parseInt(extractLimit.value, 10) || 0 : 0,
        position: genForm.position.value,
        report_type: genForm.report_type.value
      };
    };

    var setExtractStatus = function (msg, bad) {
      if (!extractStatus) return;
      extractStatus.textContent = msg || "";
      extractStatus.classList.toggle("err", !!bad);
    };

    /* ---------- 大图自动压缩，避免上传失败 ---------- */
    var compressImage = function (file) {
      if (!file.type || file.type.indexOf("image/") !== 0) return Promise.resolve(file);
      if (file.size < 1.5 * 1024 * 1024) return Promise.resolve(file);
      return new Promise(function (resolve) {
        var img = new Image();
        var url = URL.createObjectURL(file);
        var done = function (out) {
          URL.revokeObjectURL(url);
          resolve(out || file);
        };
        img.onload = function () {
          var max = 1800;
          var scale = Math.min(1, max / Math.max(img.naturalWidth || 1, img.naturalHeight || 1));
          var canvas = document.createElement("canvas");
          canvas.width = Math.max(1, Math.round((img.naturalWidth || 1) * scale));
          canvas.height = Math.max(1, Math.round((img.naturalHeight || 1) * scale));
          canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
          canvas.toBlob(function (blob) {
            if (!blob || blob.size >= file.size) {
              done(file);
              return;
            }
            done(new File([blob], (file.name || "image").replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" }));
          }, "image/jpeg", 0.85);
        };
        img.onerror = function () { done(file); };
        img.src = url;
      });
    };

    /* ---------- 预览确认 ---------- */
    var previewBox = $("#extract-preview");
    var previewList = $("#extract-preview-list");
    var uploadList = $("#upload-list");
    var previewApply = $("#extract-preview-apply");
    var previewRetry = $("#extract-preview-retry");
    var previewCancel = $("#extract-preview-cancel");
    var pending = [];

    var hidePreview = function () {
      if (previewBox) previewBox.classList.add("hidden");
      pending = [];
      if (previewList) previewList.innerHTML = "";
    };

    var renderPreview = function () {
      if (!previewList) return;
      previewList.innerHTML = "";
      pending.forEach(function (item, idx) {
        var block = document.createElement("div");
        block.className = "preview-item";
        var head = document.createElement("p");
        head.className = "preview-item-head";
        head.textContent = (pending.length > 1 ? "第 " + (idx + 1) + "／" + pending.length + " 份 · " : "") + item.label + " · " + item.note;
        var area = document.createElement("textarea");
        area.rows = 5;
        area.value = item.text;
        area.addEventListener("input", function () { item.text = area.value; });
        block.appendChild(head);
        block.appendChild(area);
        previewList.appendChild(block);
      });
    };

    var addResult = function (data, label) {
      pending.push({
        raw: data.raw_text || data.text || "",
        text: data.text || "",
        label: label || "素材",
        note: previewSummary(data)
      });
      renderPreview();
      if (previewBox) previewBox.classList.remove("hidden");
    };

    /* ---------- 上传进度条 ---------- */
    var createRow = function (name, size) {
      var row = document.createElement("div");
      row.className = "upload-row";
      var top = document.createElement("div");
      top.className = "upload-row-top";
      var title = document.createElement("span");
      title.className = "upload-name";
      title.textContent = name;
      var note = document.createElement("span");
      note.className = "upload-note";
      note.textContent = size ? (size / 1024 / 1024).toFixed(1) + "MB" : "";
      top.appendChild(title);
      top.appendChild(note);
      var bar = document.createElement("div");
      bar.className = "upload-bar";
      var fill = document.createElement("i");
      bar.appendChild(fill);
      row.appendChild(top);
      row.appendChild(bar);
      if (uploadList) uploadList.appendChild(row);
      return { row: row, note: note, fill: fill };
    };

    var updateRow = function (handle, pct, note, state) {
      if (!handle) return;
      handle.row.className = "upload-row" + (state ? " " + state : "");
      handle.fill.style.width = Math.max(0, Math.min(100, pct)) + "%";
      if (note) handle.note.textContent = note;
    };

    var previewSummary = function (data) {
      if (data.summary_error) {
        return "提炼失败，以下是原文（" + data.chars + " 字）：" + data.summary_error;
      }
      if (data.summarized) {
        return "提炼完成：原文 " + data.raw_chars + " 字 → " + data.chars + " 字（目标 " + data.limit + " 字），确认后填入输入框";
      }
      if (data.limit) {
        return "原文 " + data.chars + " 字，未超过 " + data.limit + " 字上限，未做精简";
      }
      return "原文 " + data.chars + " 字（不提炼），确认后填入输入框";
    };

    var showPreview = function (data, label) {
      addResult(data, label);
    };

    if (previewApply) {
      previewApply.addEventListener("click", function () {
        var parts = pending.map(function (item) { return (item.text || "").trim(); }).filter(Boolean);
        if (!parts.length) {
          setExtractStatus("分析结果为空，请重新导入", true);
          return;
        }
        var text = parts.join("\n\n");
        var cur = (briefEl.value || "").trim();
        briefEl.value = cur ? cur + "\n\n" + text : text;
        briefEl.dispatchEvent(new Event("input"));
        setExtractStatus("已填入 " + parts.length + " 份素材的分析结果，共 " + text.length + " 字");
        hidePreview();
      });
    }

    if (previewCancel) {
      previewCancel.addEventListener("click", function () {
        hidePreview();
        setExtractStatus("已取消导入");
      });
    }

    if (previewRetry) {
      previewRetry.addEventListener("click", async function () {
        if (!pending.length) return;
        var opts = extractOptions();
        if (!opts.limit) {
          setExtractStatus("当前选择是不提炼，以上即为原文", true);
          return;
        }
        previewRetry.disabled = true;
        try {
          for (var i = 0; i < pending.length; i++) {
            setExtractStatus("正在重新分析第 " + (i + 1) + "／" + pending.length + " 份…");
            try {
              var res = await apiPost("/api/summarize", {
                text: pending[i].raw,
                limit: opts.limit,
                position: opts.position,
                report_type: opts.report_type
              });
              var data = await res.json();
              pending[i].text = data.text || pending[i].text;
              pending[i].note = previewSummary(data);
            } catch (err) {
              pending[i].note = "重新分析失败：" + (err.message || "请稍后重试");
            }
          }
          renderPreview();
          setExtractStatus("已按 " + opts.limit + " 字重新分析 " + pending.length + " 份素材");
        } finally {
          previewRetry.disabled = false;
        }
      });
    }

    var uploadFile = function (file, opts, row) {
      return new Promise(function (resolve, reject) {
        var fd = new FormData();
        fd.append("file", file);
        fd.append("limit", String(opts.limit));
        fd.append("position", opts.position);
        fd.append("report_type", opts.report_type);
        var xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/extract");
        xhr.upload.onprogress = function (ev) {
          if (!ev.lengthComputable) return;
          var pct = Math.min(90, Math.round((ev.loaded / ev.total) * 90));
          updateRow(row, pct, "上传中 " + pct + "%");
        };
        xhr.upload.onload = function () {
          updateRow(row, 90, opts.limit ? "上传完成，正在分析总结…" : "上传完成，正在解析…", "busy");
        };
        xhr.onload = function () {
          var data = {};
          try { data = JSON.parse(xhr.responseText || "{}"); } catch (e) { /* 忽略 */ }
          if (xhr.status >= 200 && xhr.status < 300) {
            updateRow(row, 100, "分析完成 · 原文 " + data.raw_chars + " 字 → " + data.chars + " 字", "done");
            resolve(data);
          } else {
            reject(new Error(data.detail || "解析失败（" + xhr.status + "）"));
          }
        };
        xhr.onerror = function () { reject(new Error("上传失败，请检查网络")); };
        xhr.send(fd);
      });
    };

    var uploadBusy = false;
    var handleFiles = async function (list) {
      var arr = Array.prototype.slice.call(list || []);
      if (!arr.length || !briefEl) return;
      if (uploadBusy) {
        setExtractStatus("上一批还在分析，请稍等…", true);
        return;
      }
      uploadBusy = true;
      var opts = extractOptions();
      var ok = 0;
      for (var i = 0; i < arr.length; i++) {
        var picked = arr[i];
        var row = createRow(picked.name || "文件", picked.size);
        try {
          var file = picked;
          if (picked.type && picked.type.indexOf("image/") === 0 && picked.size > 1.5 * 1024 * 1024) {
            updateRow(row, 0, "图片较大，正在压缩…");
            file = await compressImage(picked);
          }
          var data = await uploadFile(file, opts, row);
          addResult(data, picked.name || "文件");
          ok += 1;
        } catch (err) {
          updateRow(row, 100, err.message || "解析失败，请稍后重试", "err");
        }
      }
      uploadBusy = false;
      if (extractFile) extractFile.value = "";
      if (ok) setExtractStatus("已分析 " + ok + " 份素材，确认后填入输入框");
      else setExtractStatus("没有成功分析的素材", true);
    };

    if (extractFile && briefEl) {
      extractFile.addEventListener("change", function () {
        handleFiles(extractFile.files);
      });
    }

    /* 拖拽上传 */
    var dropZone = $("#extract-drop");
    if (dropZone) {
      var markOver = function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        dropZone.classList.add("over");
      };
      var clearOver = function (ev) {
        if (ev) {
          ev.preventDefault();
          ev.stopPropagation();
        }
        dropZone.classList.remove("over");
      };
      ["dragenter", "dragover"].forEach(function (name) { dropZone.addEventListener(name, markOver); });
      ["dragleave", "dragend"].forEach(function (name) { dropZone.addEventListener(name, clearOver); });
      dropZone.addEventListener("drop", function (ev) {
        clearOver(ev);
        var dt = ev.dataTransfer;
        if (dt && dt.files && dt.files.length) handleFiles(dt.files);
      });
      // 文件拖到上传框外面时，避免浏览器直接打开文件
      document.addEventListener("dragover", function (ev) {
        var types = (ev.dataTransfer && ev.dataTransfer.types) || [];
        if (Array.prototype.indexOf.call(types, "Files") >= 0) ev.preventDefault();
      });
      document.addEventListener("drop", function (ev) {
        if (ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files.length) ev.preventDefault();
      });
    }

    var pullLink = async function () {
      if (!extractUrl || !briefEl) return;
      var url = (extractUrl.value || "").trim();
      if (!url) {
        setExtractStatus("请先粘贴网页链接", true);
        return;
      }
      if (extractUrlBtn) extractUrlBtn.disabled = true;
      var opts = extractOptions();
      setExtractStatus(opts.limit ? "正在读取网页并分析总结…" : "正在读取网页正文…");
      try {
        var res = await apiPost("/api/extract-url", {
          url: url,
          limit: opts.limit,
          position: opts.position,
          report_type: opts.report_type
        });
        var data = await res.json();
        showPreview(data, "链接正文");
        setExtractStatus("已抓取并分析链接正文：" + data.chars + " 字，确认后填入输入框");
        extractUrl.value = "";
      } catch (err) {
        setExtractStatus(err.message || "读取失败，请稍后重试", true);
      } finally {
        if (extractUrlBtn) extractUrlBtn.disabled = false;
      }
    };
    if (extractUrlBtn) extractUrlBtn.addEventListener("click", pullLink);
    if (extractUrl) {
      extractUrl.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") {
          ev.preventDefault();
          pullLink();
        }
      });
    }

    /* ---------- 语音输入：按住说话转文字 ---------- */
    var voiceBtn = $("#voice-btn");
    if (voiceBtn && briefEl) {
      var voiceState = "idle";
      var audioCtx = null;
      var mediaStream = null;
      var scriptNode = null;
      var voiceChunks = [];
      var voiceSampleRate = 44100;
      var voiceTimer = null;
      var MAX_REC_MS = 30000;

      var setVoiceState = function (state) {
        voiceState = state;
        var label = voiceBtn.querySelector(".voice-label");
        voiceBtn.classList.remove("recording", "uploading");
        if (state === "recording") {
          voiceBtn.classList.add("recording");
          if (label) label.textContent = "松开结束";
        } else if (state === "uploading") {
          voiceBtn.classList.add("uploading");
          if (label) label.textContent = "识别中…";
        } else if (label) {
          label.textContent = "按住说话";
        }
      };

      var resample = function (buffer, fromRate, toRate) {
        var ratio = fromRate / toRate;
        var newLength = Math.max(1, Math.round(buffer.length / ratio));
        var out = new Float32Array(newLength);
        for (var i = 0; i < newLength; i++) {
          var src = i * ratio;
          var idx = Math.floor(src);
          var frac = src - idx;
          var a = buffer[idx] || 0;
          var b = buffer[idx + 1] || 0;
          out[i] = a + (b - a) * frac;
        }
        return out;
      };

      var encodeWAV = function (chunks, sampleRate) {
        var length = 0;
        chunks.forEach(function (c) { length += c.length; });
        var buffer = new Float32Array(length);
        var offset = 0;
        chunks.forEach(function (c) { buffer.set(c, offset); offset += c.length; });

        // 重采样到 16kHz：语音识别标准采样率，体积缩小约 2/3，加快上传与返回
        var TARGET_RATE = 16000;
        if (sampleRate > TARGET_RATE) {
          buffer = resample(buffer, sampleRate, TARGET_RATE);
          sampleRate = TARGET_RATE;
        }

        var numChannels = 1;
        var bytesPerSample = 2;
        var blockAlign = numChannels * bytesPerSample;
        var dataSize = buffer.length * bytesPerSample;
        var arrayBuffer = new ArrayBuffer(44 + dataSize);
        var view = new DataView(arrayBuffer);

        var writeString = function (pos, str) {
          for (var i = 0; i < str.length; i++) view.setUint8(pos + i, str.charCodeAt(i));
        };

        writeString(0, "RIFF");
        view.setUint32(4, 36 + dataSize, true);
        writeString(8, "WAVE");
        writeString(12, "fmt ");
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, numChannels, true);
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, sampleRate * blockAlign, true);
        view.setUint16(32, blockAlign, true);
        view.setUint16(34, 16, true);
        writeString(36, "data");
        view.setUint32(40, dataSize, true);

        for (var i = 0; i < buffer.length; i++) {
          var s = Math.max(-1, Math.min(1, buffer[i]));
          view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        }
        return new Blob([arrayBuffer], { type: "audio/wav" });
      };

      var uploadVoice = async function (blob) {
        try {
          var fd = new FormData();
          fd.append("file", blob, "voice.wav");
          var res = await fetch("/api/transcribe", { method: "POST", body: fd });
          var data = {};
          try { data = await res.json(); } catch (e) { /* 忽略 */ }
          if (!res.ok) throw new Error(data.detail || "转写失败，请重试");
          var text = (data.text || "").trim();
          if (!text) throw new Error("没有识别到内容，请重新说一次");
          var current = briefEl.value.trim();
          briefEl.value = current ? current + "\n" + text : text;
          briefEl.focus();
          briefEl.dispatchEvent(new Event("input"));
          var autoGen = $("#voice-auto");
          if (autoGen && autoGen.checked) {
            if (draftTip) draftTip.textContent = "已识别，正在自动生成…";
            genForm.requestSubmit();
          } else if (draftTip) {
            draftTip.textContent = "已识别并填入输入框，点「一键生成汇报」完成转化";
          }
        } catch (err) {
          if (draftTip) draftTip.textContent = err.message || "语音转写失败";
        } finally {
          setVoiceState("idle");
        }
      };

      var playBeep = function () {
        try {
          var AC2 = window.AudioContext || window.webkitAudioContext;
          if (!AC2) return;
          var c = new AC2();
          var osc = c.createOscillator();
          var gain = c.createGain();
          osc.type = "sine";
          osc.frequency.value = 1000;
          var t = c.currentTime;
          gain.gain.setValueAtTime(0.0001, t);
          gain.gain.exponentialRampToValueAtTime(0.35, t + 0.015);
          gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.13);
          osc.connect(gain);
          gain.connect(c.destination);
          osc.start(t);
          osc.stop(t + 0.15);
          osc.onended = function () { try { c.close(); } catch (e) { /* 忽略 */ } };
        } catch (e) { /* 忽略 */ }
      };

      var vibrate = function (pattern) {
        try {
          if (navigator.vibrate) navigator.vibrate(pattern);
        } catch (e) { /* 忽略 */ }
      };

      var stopVoice = function () {
        if (voiceState !== "recording") return;
        playBeep();
        vibrate(20);
        if (voiceTimer) { clearTimeout(voiceTimer); voiceTimer = null; }
        try { scriptNode.disconnect(); } catch (e) { /* 忽略 */ }
        try { mediaStream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) { /* 忽略 */ }
        try { audioCtx.close(); } catch (e) { /* 忽略 */ }
        var wav = encodeWAV(voiceChunks, voiceSampleRate);
        voiceChunks = [];
        setVoiceState("uploading");
        uploadVoice(wav);
      };

      var startVoice = async function (ev) {
        if (ev && ev.cancelable) ev.preventDefault();
        if (voiceState !== "idle") return;
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          if (draftTip) draftTip.textContent = "当前浏览器不支持语音输入，请用手机浏览器打开";
          return;
        }
        try {
          mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (e) {
          if (draftTip) draftTip.textContent = "无法访问麦克风，请在浏览器设置里允许麦克风权限";
          return;
        }
        var AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) {
          try { mediaStream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) { /* 忽略 */ }
          if (draftTip) draftTip.textContent = "当前浏览器不支持录音，请用手机浏览器打开";
          return;
        }
        audioCtx = new AC();
        if (audioCtx.state === "suspended") { try { await audioCtx.resume(); } catch (e) { /* 忽略 */ } }
        var source = audioCtx.createMediaStreamSource(mediaStream);
        scriptNode = audioCtx.createScriptProcessor(4096, 1, 1);
        voiceChunks = [];
        voiceSampleRate = audioCtx.sampleRate || 44100;
        scriptNode.onaudioprocess = function (e) {
          var input = e.inputBuffer.getChannelData(0);
          var copy = new Float32Array(input.length);
          copy.set(input);
          voiceChunks.push(copy);
        };
        source.connect(scriptNode);
        scriptNode.connect(audioCtx.destination);
        setVoiceState("recording");
        playBeep();
        vibrate(30);
        voiceTimer = setTimeout(stopVoice, MAX_REC_MS);
      };

      voiceBtn.addEventListener("touchstart", startVoice, { passive: false });
      voiceBtn.addEventListener("touchend", function (ev) { ev.preventDefault(); stopVoice(); }, { passive: false });
      voiceBtn.addEventListener("touchcancel", stopVoice);
      voiceBtn.addEventListener("mousedown", startVoice);
      voiceBtn.addEventListener("mouseup", stopVoice);
      voiceBtn.addEventListener("mouseleave", stopVoice);
      voiceBtn.addEventListener("contextmenu", function (ev) { ev.preventDefault(); });
    }

    var frameBtn = genForm.querySelector("[data-brief-frame]");
    if (frameBtn && briefEl) {
      var frameText = "本周完成：\n1. \n2. \n3. \n\n遇到的问题：\n1. \n\n下周计划：\n1. \n\n需要的支持：\n1. ";
      frameBtn.addEventListener("click", function () {
        var current = briefEl.value.trim();
        briefEl.value = current ? current + "\n\n" + frameText : frameText;
        briefEl.focus();
        briefEl.dispatchEvent(new Event("input"));
      });
    }

    var clearBtn = genForm.querySelector("[data-brief-clear]");
    if (clearBtn && briefEl) {
      clearBtn.addEventListener("click", function () {
        briefEl.value = "";
        briefEl.focus();
        try { localStorage.removeItem(draftKey); } catch (e) { /* 忽略 */ }
        if (draftTip) draftTip.textContent = "已清空草稿。";
      });
    }

    /* ---------- 本周素材收集箱 ---------- */
    var baseKey = "workbrief." + (genForm.getAttribute("data-code") || "guest");
    var inboxKey = baseKey + ".inbox";
    var tplKey = baseKey + ".tpl";
    var lsGet = function (key, fallback) {
      try {
        var raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : fallback;
      } catch (e) { return fallback; }
    };
    var lsSet = function (key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* 忽略 */ }
    };

    var inboxList = $("#inbox-list");
    var inboxCount = $("#inbox-count");
    var inboxInput = $("#inbox-input");
    var inboxItems = lsGet(inboxKey, []);
    if (!Array.isArray(inboxItems)) inboxItems = [];

    var renderInbox = function () {
      if (!inboxList) return;
      inboxList.innerHTML = "";
      if (!inboxItems.length) {
        var empty = document.createElement("li");
        empty.className = "inbox-empty";
        empty.textContent = "还没有碎片。周中随手记一句，周五汇总。";
        inboxList.appendChild(empty);
      } else {
        inboxItems.forEach(function (item, idx) {
          var li = document.createElement("li");
          var span = document.createElement("span");
          span.textContent = item;
          var del = document.createElement("button");
          del.type = "button";
          del.setAttribute("data-index", String(idx));
          del.setAttribute("aria-label", "删除这条碎片");
          del.textContent = "×";
          li.appendChild(span);
          li.appendChild(del);
          inboxList.appendChild(li);
        });
      }
      if (inboxCount) inboxCount.textContent = inboxItems.length + " 条";
    };

    var addInbox = function () {
      if (!inboxInput) return;
      var value = inboxInput.value.trim().slice(0, 120);
      if (!value) return;
      if (inboxItems.indexOf(value) === -1) inboxItems.unshift(value);
      if (inboxItems.length > 40) inboxItems.length = 40;
      lsSet(inboxKey, inboxItems);
      inboxInput.value = "";
      renderInbox();
    };

    var inboxAddBtn = $("#inbox-add");
    if (inboxAddBtn) inboxAddBtn.addEventListener("click", addInbox);
    if (inboxInput) {
      inboxInput.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") { ev.preventDefault(); addInbox(); }
      });
    }
    if (inboxList) {
      inboxList.addEventListener("click", function (ev) {
        var btn = ev.target.closest("button[data-index]");
        if (!btn) return;
        inboxItems.splice(parseInt(btn.getAttribute("data-index"), 10), 1);
        lsSet(inboxKey, inboxItems);
        renderInbox();
      });
    }

    var inboxMerge = $("#inbox-merge");
    if (inboxMerge && briefEl) {
      inboxMerge.addEventListener("click", function () {
        if (!inboxItems.length) {
          if (draftTip) draftTip.textContent = "收集箱还是空的，先记一条。";
          return;
        }
        var block = inboxItems.map(function (item) { return "- " + item; }).join("\n");
        var current = briefEl.value.trim();
        briefEl.value = current ? current + "\n\n" + block : block;
        var count = inboxItems.length;
        inboxItems = [];
        lsSet(inboxKey, inboxItems);
        renderInbox();
        briefEl.focus();
        briefEl.dispatchEvent(new Event("input"));
        if (draftTip) draftTip.textContent = "已把 " + count + " 条碎片汇总到输入框。";
      });
    }

    var inboxClear = $("#inbox-clear");
    if (inboxClear) {
      inboxClear.addEventListener("click", function () {
        inboxItems = [];
        lsSet(inboxKey, inboxItems);
        renderInbox();
        if (draftTip) draftTip.textContent = "收集箱已清空。";
      });
    }

    renderInbox();

    /* ---------- 历史模板复用 ---------- */
    var tplRow = $("#tpl-row");
    var tplSelect = $("#tpl-select");
    var templates = lsGet(tplKey, []);
    if (!Array.isArray(templates)) templates = [];

    var renderTpl = function () {
      if (!tplRow || !tplSelect) return;
      tplSelect.innerHTML = "";
      templates.forEach(function (tpl, idx) {
        var opt = document.createElement("option");
        opt.value = String(idx);
        opt.textContent = tpl.name;
        tplSelect.appendChild(opt);
      });
      tplRow.classList.toggle("hidden", templates.length === 0);
    };

    var tplSaveBtn = genForm.querySelector("[data-brief-save-tpl]");
    if (tplSaveBtn && briefEl) {
      tplSaveBtn.addEventListener("click", function () {
        var text = briefEl.value.trim();
        if (!text) {
          if (draftTip) draftTip.textContent = "先写点内容，再存为模板。";
          return;
        }
        var firstLine = text.split("\n")[0].replace(/[：:。；;]/g, "").trim();
        var name = (firstLine || "未命名模板").slice(0, 14);
        var existing = -1;
        templates.forEach(function (tpl, idx) { if (tpl.text === text) existing = idx; });
        if (existing >= 0) templates.splice(existing, 1);
        templates.unshift({ name: name, text: text, at: Date.now() });
        if (templates.length > 10) templates.length = 10;
        lsSet(tplKey, templates);
        renderTpl();
        if (draftTip) draftTip.textContent = "已存为模板：" + name;
      });
    }

    var tplApply = $("#tpl-apply");
    if (tplApply && tplSelect && briefEl) {
      tplApply.addEventListener("click", function () {
        var tpl = templates[parseInt(tplSelect.value, 10)];
        if (!tpl) return;
        briefEl.value = tpl.text;
        briefEl.focus();
        briefEl.dispatchEvent(new Event("input"));
        if (draftTip) draftTip.textContent = "已套用模板：" + tpl.name;
      });
    }

    var tplDel = $("#tpl-del");
    if (tplDel && tplSelect) {
      tplDel.addEventListener("click", function () {
        var idx = parseInt(tplSelect.value, 10);
        if (isNaN(idx)) return;
        templates.splice(idx, 1);
        lsSet(tplKey, templates);
        renderTpl();
        if (draftTip) draftTip.textContent = "已删除该模板。";
      });
    }

    renderTpl();

    /* ---------- 粘贴内容智能分段 ---------- */
    var organizeBrief = function (raw) {
      var rules = [
        { key: "plan", re: /下周|下星期|明天|计划|准备|预计|接下来/ },
        { key: "help", re: /支持|协助|需要|协调|资源|审批|配合|推动/ },
        { key: "risk", re: /问题|风险|阻塞|卡点|延期|异常|故障|投诉|客诉|bug|缺口/i }
      ];
      var buckets = { done: [], risk: [], plan: [], help: [] };
      raw.split(/\n+|[；;]+/).forEach(function (line) {
        var text = line
          .replace(/^\s*(?:\[?\d{1,2}:\d{2}\]?|\d{1,2}月\d{1,2}日|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\s*/, "")
          .replace(/^\s*@[^\s]{1,12}\s+/, "")
          .replace(/^\s*[@\-•*·]\s*/, "")
          .replace(/^\s*\d{1,2}[.、)]\s*/, "")
          .replace(/^\s*[\u4e00-\u9fa5A-Za-z0-9_\-]{1,10}[：:]\s*/, "")
          .trim();
        if (text.length < 2) return;
        if (text.length > 140) text = text.slice(0, 140);
        var bucket = "done";
        for (var i = 0; i < rules.length; i++) {
          if (rules[i].re.test(text)) { bucket = rules[i].key; break; }
        }
        buckets[bucket].push(text);
      });
      var titles = { done: "本周完成", risk: "问题与风险", plan: "下周计划", help: "需要的支持" };
      var parts = [];
      ["done", "risk", "plan", "help"].forEach(function (key) {
        if (!buckets[key].length) return;
        parts.push(titles[key] + "：\n" + buckets[key].map(function (item, idx) {
          return (idx + 1) + ". " + item;
        }).join("\n"));
      });
      return parts.join("\n\n");
    };

    var parseBtn = genForm.querySelector("[data-brief-parse]");
    if (parseBtn && briefEl) {
      parseBtn.addEventListener("click", function () {
        var raw = briefEl.value.trim();
        if (!raw) {
          if (draftTip) draftTip.textContent = "先把聊天记录或待办粘贴进来。";
          return;
        }
        var organized = organizeBrief(raw);
        if (!organized) return;
        briefEl.value = organized;
        briefEl.focus();
        briefEl.dispatchEvent(new Event("input"));
        if (draftTip) draftTip.textContent = "已按完成 / 问题 / 计划 / 支持四段整理。";
      });
    }

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
          extra: genForm.extra.value,
          link_prev: genForm.link_prev ? genForm.link_prev.checked : true
        });
        await streamSSE(res, function (data) {
          if (data.type === "chunk") {
            streamText.textContent += data.text;
          } else if (data.type === "error") {
            genStatus.className = "status err";
            genStatus.textContent = data.message;
          } else if (data.type === "done") {
            try { localStorage.removeItem(draftKey); } catch (e) { /* 忽略 */ }
            try { localStorage.setItem("workbrief.lastdone", String(Date.now())); } catch (e) { /* 忽略 */ }
            if (data.trial) {
              genStatus.className = "status ok";
              genStatus.textContent = data.remaining > 0
                ? "试用生成完成，还可试用 " + data.remaining + " 次（试用报告不保存）"
                : "试用次数已用完，激活兑换码后可继续使用";
              show(document.getElementById("result-actions"));
              var tipEl = document.getElementById("stream-tip");
              if (tipEl) tipEl.textContent = "试用报告不会保存。激活兑换码后可保存历史、继续微调和导出 Word。";
              if (data.remaining <= 0) {
                trialExhausted = true;
                genBtn.textContent = "试用已用完，请先激活兑换码";
                genBtn.disabled = true;
              }
            } else {
              genStatus.className = "status ok";
              genStatus.textContent = data.remaining < 0
                ? "生成完成，无限次数，正在打开…"
                : "生成完成，剩余 " + data.remaining + " 次，正在打开…";
              window.location.href = "/reports/" + data.report_id;
            }
          }
        });
      } catch (err) {
        genStatus.className = "status err";
        genStatus.textContent = err.message;
      } finally {
        genBtn.disabled = trialExhausted;
      }
    });

    var copyBtn = $("#copy-btn");
    if (copyBtn) {
      copyBtn.addEventListener("click", async function () {
        var content = (streamText.textContent || "").trim();
        if (!content) return;
        try {
          await navigator.clipboard.writeText(content);
          copyBtn.textContent = "已复制";
        } catch (e) {
          var range = document.createRange();
          range.selectNodeContents(streamText);
          var sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
          copyBtn.textContent = "已选中，按 Ctrl+C";
        }
        setTimeout(function () { copyBtn.textContent = "复制全文"; }, 2000);
      });
    }
  }

  /* ---------------- 报告详情：手动编辑标题/正文 ---------------- */
  var editForm = $("#edit-form");
  if (editForm) {
    var editBtn = $("#edit-btn");
    var editStatus = $("#edit-status");
    var editTitle = editForm.querySelector('[name="title"]');
    var editContent = editForm.querySelector('[name="content"]');
    var editInitial = { title: editTitle.value, content: editContent.value };

    var resetBtn = $("#edit-reset");
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        editTitle.value = editInitial.title;
        editContent.value = editInitial.content;
        editStatus.className = "status";
        editStatus.textContent = "已撤销未保存的改动";
      });
    }

    editForm.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      var title = editTitle.value.trim();
      var content = editContent.value.trim();
      if (!title) {
        editStatus.className = "status err";
        editStatus.textContent = "标题不能为空";
        editTitle.focus();
        return;
      }
      if (content.length < 10) {
        editStatus.className = "status err";
        editStatus.textContent = "正文太短，至少写 10 个字";
        editContent.focus();
        return;
      }

      editBtn.disabled = true;
      editStatus.className = "status";
      editStatus.textContent = "正在保存…";
      try {
        await apiPost("/api/reports/" + editForm.getAttribute("data-report-id") + "/edit", {
          title: title,
          content: content
        });
        editStatus.className = "status ok";
        editStatus.textContent = "已保存，正在刷新…";
        window.location.reload();
      } catch (err) {
        editStatus.className = "status err";
        editStatus.textContent = err.message;
      } finally {
        editBtn.disabled = false;
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

  /* ---------------- 周一补周报提醒 ---------------- */
  var weekReminder = document.getElementById("week-reminder");
  if (weekReminder) {
    var now = new Date();
    var lastDone = 0;
    try { lastDone = parseInt(localStorage.getItem("workbrief.lastdone") || "0", 10) || 0; } catch (e) { /* 忽略 */ }
    var dayKey = now.getFullYear() + "-" + (now.getMonth() + 1) + "-" + now.getDate();
    var dismissed = false;
    try { dismissed = localStorage.getItem("workbrief.monday." + dayKey) === "1"; } catch (e) { /* 忽略 */ }
    var freshEnough = lastDone && (now.getTime() - lastDone) < 6 * 24 * 60 * 60 * 1000;
    if (now.getDay() === 1 && !dismissed && !freshEnough) {
      weekReminder.classList.remove("hidden");
      var reminderOk = document.getElementById("week-reminder-ok");
      if (reminderOk) {
        reminderOk.addEventListener("click", function () {
          weekReminder.classList.add("hidden");
          try { localStorage.setItem("workbrief.monday." + dayKey, "1"); } catch (e) { /* 忽略 */ }
        });
      }
    }
  }

  /* ---------------- 购买：生成订单 + 自动轮询发码 ---------------- */
  var orderForm = $("#order-form");
  if (orderForm) {
    var orderBtn = $("#order-btn");
    var orderStatus = $("#order-status");
    var orderResult = $("#order-result");
    var orderNoEl = $("#order-no");
    var orderTip = $("#order-tip");
    var orderBadge = $("#order-badge");
    var orderBadgeText = $("#order-badge-text");
    var orderTitle = $("#order-title");
    var orderWaiting = $("#order-waiting");
    var orderCodeWrap = $("#order-code-wrap");
    var orderClaimRow = $("#order-claim-row");
    var orderClaim = $("#order-claim");
    var orderClaimStatus = $("#order-claim-status");
    var orderQr = $("#order-qr");
    var orderQrLabel = $("#order-qr-label");
    var autoConfirm = orderForm.getAttribute("data-auto-confirm") === "1";
    var activeOrder = null;
    var pollTimer = null;
    var pollTicks = 0;

    var stopPoll = function () {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    };

    var setOrderUrl = function (no) {
      try {
        var url = new URL(location.href);
        if (no) url.searchParams.set("order", no);
        else url.searchParams.delete("order");
        history.replaceState(null, "", url.toString());
      } catch (e) { /* 老浏览器忽略 */ }
    };

    var syncTabs = function (channel) {
      channel = channel === "wxpay" ? "wxpay" : "alipay";
      payChannel = channel;
      document.querySelectorAll(".pay-tab").forEach(function (tab) {
        var on = tab.getAttribute("data-channel") === channel;
        tab.classList.toggle("on", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
      });
      document.querySelectorAll(".qr-stage").forEach(function (stage) {
        stage.classList.toggle("hidden", stage.getAttribute("data-stage") !== channel);
      });
      var sumChannel = document.getElementById("sum-channel");
      if (sumChannel) sumChannel.textContent = channel === "wxpay" ? "微信支付" : "支付宝";
    };

    var tipText = function () {
      var wechat = orderResult.getAttribute("data-wechat") || "";
      if (autoConfirm) return "支付完成后页面会自动确认到账并出码，通常几秒内完成。";
      if (wechat) {
        return "扫码付款后，备注填订单号后 4 位；点「我已付款」通知客服，核对后自动出码。也可把订单号发微信 " + wechat + "。";
      }
      return "扫码付款后，备注填订单号后 4 位；点「我已付款」通知客服，核对后页面自动出码。";
    };

    var showWaiting = function (data) {
      orderBadge.className = "order-badge waiting";
      orderBadgeText.textContent = "等待到账";
      orderTitle.textContent = "等待付款";
      hide(orderCodeWrap);
      show(orderWaiting);
      show(orderClaimRow);
      orderClaim.disabled = false;
      if (data && data.claimed) {
        orderClaim.textContent = "已通知，等待确认";
        orderClaimStatus.textContent = "已通知客服，核对到账后会自动出码";
      } else {
        orderClaim.textContent = "我已付款，通知确认";
        orderClaimStatus.textContent = "付款完成后点一下，客服会优先核对";
      }
      show(orderResult);
    };

    var showPaid = function (data) {
      stopPoll();
      orderBadge.className = "order-badge paid";
      orderBadgeText.textContent = "已到账";
      orderTitle.textContent = "付款成功";
      hide(orderWaiting);
      hide(orderClaimRow);
      $("#order-code").textContent = data.code;
      $("#order-code-uses").textContent = data.uses;
      $("#order-activate").setAttribute(
        "href",
        data.activate_url || ("/activate?code=" + encodeURIComponent(data.code))
      );
      show(orderCodeWrap);
      orderCodeWrap.classList.remove("pop");
      void orderCodeWrap.offsetWidth;
      orderCodeWrap.classList.add("pop");
      orderStatus.className = "status ok";
      orderStatus.textContent = "已到账，" + data.uses + " 次兑换码已发放";
      var queryInput = $("#query-no");
      if (queryInput) queryInput.value = data.order_no;
      setOrderUrl(data.order_no);
    };

    var renderOrder = function (data) {
      activeOrder = { order_no: data.order_no, channel: data.channel || payChannel };
      syncTabs(activeOrder.channel);
      orderNoEl.textContent = data.order_no;
      $("#order-amount").textContent = "¥" + data.amount;
      $("#order-uses").textContent = data.uses + " 次";
      $("#order-code-uses").textContent = data.uses;
      orderQrLabel.textContent = data.channel_label || "";
      if (data.qr_url) {
        if (orderQr.getAttribute("src") !== data.qr_url) orderQr.src = data.qr_url;
        show(orderQr);
      } else {
        hide(orderQr);
      }
      orderTip.textContent = tipText();
      var queryInput = $("#query-no");
      if (queryInput) queryInput.value = data.order_no;
      if (data.code) showPaid(data);
      else showWaiting(data);
    };

    var pollOrder = function () {
      if (!activeOrder) return;
      pollTicks += 1;
      if (pollTicks > 400) { stopPoll(); return; }
      fetch("/api/orders/" + encodeURIComponent(activeOrder.order_no))
        .then(function (res) {
          if (res.status === 404) { stopPoll(); return null; }
          return res.ok ? res.json() : null;
        })
        .then(function (data) {
          if (!data) return;
          if (data.code) showPaid(data);
        })
        .catch(function () { /* 网络抖动时保持轮询 */ });
    };

    var startPoll = function () {
      stopPoll();
      pollTicks = 0;
      pollTimer = setInterval(pollOrder, 3000);
    };

    var createOrder = async function (silent) {
      var picked = orderForm.querySelector('input[name="plan_id"]:checked');
      if (!picked) {
        orderStatus.className = "status err";
        orderStatus.textContent = "请先选择套餐";
        return;
      }

      stopPoll();
      pollTicks = 0;
      orderBtn.disabled = true;
      if (!silent) {
        orderStatus.className = "status";
        orderStatus.textContent = "正在生成订单…";
      }
      try {
        var res = await apiPost("/api/orders", { plan_id: picked.value, channel: payChannel });
        var data = await res.json();
        renderOrder(data);
        setOrderUrl(data.order_no);
        orderStatus.className = "status ok";
        orderStatus.textContent = silent
          ? "已切换为" + (data.channel_label || "") + "，新订单 " + data.order_no
          : "订单已生成，请扫码付款";
        orderResult.scrollIntoView({ behavior: "smooth", block: "center" });
        if (data.pay_url) window.open(data.pay_url, "_blank");
        startPoll();
      } catch (err) {
        orderStatus.className = "status err";
        orderStatus.textContent = err.message || "生成订单失败，请稍后重试";
      } finally {
        orderBtn.disabled = false;
      }
    };

    orderBtn.addEventListener("click", function () { createOrder(false); });

    // 换支付方式时，把待付款订单一起换成新渠道，避免扫错码
    document.addEventListener("paychannelchange", function (ev) {
      if (!activeOrder) return;
      if (activeOrder.channel === ev.detail) return;
      if (!orderCodeWrap.classList.contains("hidden")) return;
      createOrder(true);
    });

    // 我已付款：记录催单，让后台优先核对
    if (orderClaim) {
      orderClaim.addEventListener("click", async function () {
        if (!activeOrder) return;
        orderClaim.disabled = true;
        orderClaimStatus.textContent = "正在通知客服…";
        try {
          var res = await fetch(
            "/api/orders/" + encodeURIComponent(activeOrder.order_no) + "/claim",
            { method: "POST" }
          );
          var data = {};
          try { data = await res.json(); } catch (e) { /* 忽略 */ }
          if (!res.ok) throw new Error(data.detail || "通知失败，请稍后重试");
          orderClaim.textContent = "已通知，等待确认";
          orderClaimStatus.textContent = "已通知客服，核对到账后会自动出码（页面每 3 秒检查）";
          pollOrder();
        } catch (err) {
          orderClaim.disabled = false;
          orderClaimStatus.textContent = err.message;
        }
      });
    }

    // 刷新后从 ?order= 恢复订单，继续轮询，不丢单
    var restoreNo = "";
    try { restoreNo = new URLSearchParams(location.search).get("order") || ""; } catch (e) { /* 忽略 */ }
    if (restoreNo) {
      orderStatus.className = "status";
      orderStatus.textContent = "正在恢复订单…";
      fetch("/api/orders/" + encodeURIComponent(restoreNo))
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) {
          if (!data) {
            orderStatus.className = "status err";
            orderStatus.textContent = "订单不存在或已失效，请重新选择套餐下单";
            return;
          }
          renderOrder(data);
          orderStatus.className = "status ok";
          orderStatus.textContent = data.code
            ? "该订单已完成，兑换码如下"
            : "已恢复订单 " + data.order_no + "，请扫码付款";
          if (!data.code) startPoll();
          orderResult.scrollIntoView({ behavior: "smooth", block: "center" });
        })
        .catch(function () {
          orderStatus.className = "status err";
          orderStatus.textContent = "网络异常，订单恢复失败，请刷新重试";
        });
    }
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
  window.zbApiPost = apiPost;
  window.zbStreamSSE = streamSSE;
})();
(function () {
  var btn = document.getElementById("agg-btn");
  if (!btn) return;
  var typeSel = document.getElementById("agg-type");
  var box = document.getElementById("agg-stream");
  var text = document.getElementById("agg-text");
  var status = document.getElementById("agg-status");

  btn.addEventListener("click", async function () {
    btn.disabled = true;
    box.classList.remove("hidden");
    text.textContent = "";
    status.className = "status";
    status.textContent = "正在汇总，约需 20-40 秒…";
    try {
      var res = await window.zbApiPost("/api/aggregate", { target_type: typeSel.value });
      await window.zbStreamSSE(res, function (data) {
        if (data.type === "chunk") {
          text.textContent += data.text;
        } else if (data.type === "progress") {
          status.textContent = data.text;
        } else if (data.type === "error") {
          status.className = "status err";
          status.textContent = data.message;
        } else if (data.type === "done") {
          status.textContent = "汇总完成，正在打开…";
          window.location.href = "/reports/" + data.report_id;
        }
      });
    } catch (err) {
      status.className = "status err";
      status.textContent = err.message || "汇总失败，请稍后重试";
    }
    btn.disabled = false;
  });
})();

/* ---------------- 报告详情：推送到群 ---------------- */
(function () {
  "use strict";

  var form = document.getElementById("push-form");
  if (!form) return;

  var btn = document.getElementById("push-btn");
  var status = document.getElementById("push-status");
  var channelSel = form.querySelector('[name="channel"]');
  var webhookInput = form.querySelector('[name="webhook"]');
  var secretInput = form.querySelector('[name="secret"]');

  var storageKey = function () {
    return "zhibao.push." + (channelSel ? channelSel.value : "feishu");
  };
  var setStatus = function (msg, ok, bad) {
    if (!status) return;
    status.className = "status" + (ok ? " ok" : bad ? " err" : "");
    status.textContent = msg || "";
  };
  var loadWebhook = function () {
    try {
      var saved = localStorage.getItem(storageKey());
      if (saved) webhookInput.value = saved;
      else webhookInput.value = "";
    } catch (e) { /* 隐私模式忽略 */ }
  };

  if (channelSel) {
    channelSel.addEventListener("change", loadWebhook);
    loadWebhook();
  }

  form.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    var webhook = (webhookInput.value || "").trim();
    if (!webhook) {
      setStatus("请先粘贴群机器人 Webhook 地址", false, true);
      webhookInput.focus();
      return;
    }
    btn.disabled = true;
    setStatus("正在发送…");
    try {
      var res = await fetch("/api/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report_id: form.getAttribute("data-report-id"),
          channel: channelSel ? channelSel.value : "feishu",
          webhook: webhook,
          secret: secretInput ? (secretInput.value || "").trim() : ""
        })
      });
      var data = await res.json().catch(function () { return {}; });
      if (!res.ok) throw new Error(data.detail || "发送失败（" + res.status + "）");
      try { localStorage.setItem(storageKey(), webhook); } catch (e) { /* 忽略 */ }
      setStatus("已发送到" + (data.channel_label || "群") + "，去群里看看", true, false);
    } catch (err) {
      setStatus(err.message || "发送失败，请检查 Webhook 是否正确", false, true);
    } finally {
      btn.disabled = false;
    }
  });
})();
