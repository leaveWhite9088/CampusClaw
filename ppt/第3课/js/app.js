(function () {
  // 左侧导航在窄屏下的抽屉开关
  var btn = document.getElementById("menuBtn");
  var sidebar = document.getElementById("sidebar");
  if (btn && sidebar) {
    btn.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });
  }

  // 右侧小节索引：按正文里的 h2（小节）/ h3.unit-sub、h3.step-h（小节内部主题）生成
  var content = document.querySelector(".content");
  if (!content) return;

  function cleanText(el) {
    var clone = el.cloneNode(true);
    var jumps = clone.querySelectorAll(".jump");
    for (var i = 0; i < jumps.length; i++) {
      jumps[i].parentNode.removeChild(jumps[i]);
    }
    return (clone.textContent || "").replace(/\s+/g, " ").trim();
  }

  var nodes = content.querySelectorAll("h2, h3.unit-sub, h3.step-h");
  var groups = [];
  var seq = 0;

  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    if (el.tagName === "H2") {
      var sec = el.closest ? el.closest("section.unit") : null;
      var target = sec || el;
      if (!target.id) target.id = "sec-" + (groups.length + 1);
      var numEl = el.querySelector(".unit-n");
      var ttlEl = el.querySelector(".unit-t");
      groups.push({
        target: target,
        num: numEl ? cleanText(numEl) : "",
        label: ttlEl ? cleanText(ttlEl) : cleanText(el),
        subs: []
      });
    } else if (groups.length) {
      if (!el.id) el.id = "sub-" + (++seq);
      groups[groups.length - 1].subs.push({ target: el, label: cleanText(el) });
    }
  }

  // 只有一个维度时不需要目录
  if (groups.length < 2) return;

  var entries = []; // 按文档顺序排列，用于滚动高亮
  var groupLis = [];

  var aside = document.createElement("aside");
  aside.className = "toc";
  aside.setAttribute("aria-label", "本页目录");

  var head = document.createElement("p");
  head.className = "toc-h";
  head.textContent = "本页目录";
  aside.appendChild(head);

  var list = document.createElement("ol");
  list.className = "toc-list";

  for (var g = 0; g < groups.length; g++) {
    var grp = groups[g];
    var li = document.createElement("li");
    li.className = "toc-l1";
    groupLis.push(li);

    var a = document.createElement("a");
    a.href = "#" + grp.target.id;
    if (grp.num) {
      var n = document.createElement("span");
      n.className = "toc-n";
      n.textContent = grp.num;
      a.appendChild(n);
    }
    var t = document.createElement("span");
    t.className = "toc-t";
    t.textContent = grp.label;
    a.appendChild(t);
    li.appendChild(a);
    entries.push({ target: grp.target, a: a, li: li });

    if (grp.subs.length) {
      var ul = document.createElement("ul");
      ul.className = "toc-sub";
      for (var s = 0; s < grp.subs.length; s++) {
        var sli = document.createElement("li");
        var sa = document.createElement("a");
        sa.href = "#" + grp.subs[s].target.id;
        sa.textContent = grp.subs[s].label;
        sli.appendChild(sa);
        ul.appendChild(sli);
        entries.push({ target: grp.subs[s].target, a: sa, li: li });
      }
      li.appendChild(ul);
    }
    list.appendChild(li);
  }
  aside.appendChild(list);

  // 包一层 .doc，让正文与右侧目录并排
  var wrap = document.createElement("div");
  wrap.className = "doc";
  content.parentNode.insertBefore(wrap, content);
  wrap.appendChild(content);
  wrap.appendChild(aside);

  var ticking = false;
  function sync() {
    ticking = false;
    var idx = 0;
    for (var i = 0; i < entries.length; i++) {
      if (entries[i].target.getBoundingClientRect().top <= 130) idx = i;
      else break;
    }
    for (var j = 0; j < entries.length; j++) {
      entries[j].a.classList.toggle("on", j === idx);
    }
    var cur = entries[idx].li;
    for (var k = 0; k < groupLis.length; k++) {
      groupLis[k].classList.toggle("current", groupLis[k] === cur);
    }
  }
  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(sync);
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  sync();
})();
