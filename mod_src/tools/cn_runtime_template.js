/* ============================================================
 * Isle of Reveries — 简体中文补丁 (runtime layer)
 * 追加到 scripts/c3runtime.js 末尾；在 C3 运行时初始化后执行。
 * 只在“显示层”替换文本：不影响游戏逻辑、存档与事件判断。
 * ============================================================ */
(function () {
	if (self.__isleCNPatched) return;
	self.__isleCNPatched = true;

	var DICT = __DICT__;                // 英文原文 -> 中文译文（精确匹配）
	var DICT_CI = __DICT_CI__;          // 小写原文 -> 中文译文（游戏把标签整串大写再渲染时用）
	var CN_CHARS = __CN_CHARS__;        // 需要字形的中文字符（按字形表顺序）
	var CHARSET_MAP = __CHARSET_MAP__;  // 原字符集 -> 扩展后的字符集
	var TYPE_CELL = __TYPE_CELL__;      // 类型名 -> 字格尺寸（强制，避免引擎默认值错位）
	// 菜单/说明类框：把“多行说明”在显示层整体下移几像素。
	// 原因：原版这一处（物品名 y=112 高 8 / 说明 y=120 高 24）两个框紧贴，行步长只有
	// 8px，而放大后的汉字墨迹 9px -> 上下贴死。扫描到的版面坐标会被游戏运行时重算覆盖，
	// 所以在钩子里按实例再推一次：只推高度 >= 16 的多行框（说明），单行的名字框不动。
	var GAP_NUDGE = __GAP_NUDGE__;      // 由构建脚本注入
	var GAPPY = __GAP_TYPES__;          // 需要处理的类型名（名字/说明这一对）
	var TYPE_CHARSET = __TYPE_CHARSET__; // 类型名 -> 与字形表配套的字符集
	var TYPE_SPACING = __TYPE_SPACING__; // 类型名 -> 字距（像素，汉字之间留缝）

	var CJK_RE = /[\u2e80-\u2fff\u3000-\u303f\u3040-\u30ff\u31c0-\u31ef\u3200-\u4dbf\u4e00-\u9fff\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef]/;

	function hasCJK(s) { return CJK_RE.test(s); }

	function lookup(s) {
		if (Object.prototype.hasOwnProperty.call(DICT, s)) return DICT[s];
		var lo = s.toLowerCase();
		if (Object.prototype.hasOwnProperty.call(DICT_CI, lo)) return DICT_CI[lo];
		return undefined;
	}

	function translate(s) {
		if (typeof s !== 'string' || s.length === 0) return s;
		if (!/[A-Za-z]/.test(s)) return s;
		var hit = lookup(s);
		if (hit !== undefined) return hit;
		// 首尾空白变体
		var t = s.trim();
		if (t !== s) {
			hit = lookup(t);
			if (hit !== undefined) return s.replace(t, hit);
		}
		// 拼接串：材料/收集物的 "<名字> x <数量>"（游戏用 and("Monster Talon x ", 数量) 拼出来）
		var mx = s.match(/^(.+?)\s+x\s+([0-9]+)$/);
		if (mx) {
			hit = lookup(mx[1]);
			if (hit !== undefined) return hit + ' x ' + mx[2];
		}
		// 游戏运行时拼接的数量句。这里只匹配已确认会显示给玩家的完整格式，
		// 避免误改 Destroy_、Num_ 等内部动画/状态标识。
		var dyn = s.match(/^Currently built: ([0-9]+)(\/1)?$/);
		if (dyn) return '当前已建：' + dyn[1] + (dyn[2] || '');
		dyn = s.match(/^Hrrmm\.\.\. You have found ([0-9]+) of the 16 bugs scattered across the Isle\.$/);
		if (dyn) return '嗯……散落全岛的16只虫子，你已经找到了' + dyn[1] + '只。';
		dyn = s.match(/^You have ([0-9]+) Leaves\. Come back when you've found ([0-9]+)!$/);
		if (dyn) return '你现在有' + dyn[1] + '片叶子。找到' + dyn[2] + '片后再来！';
		dyn = s.match(/^Lief has ([0-9]+) Goddess Seeds?\.$/);
		if (dyn) return '利夫拥有' + dyn[1] + '颗女神种子。';
		dyn = s.match(/^Lief has ([0-9]+) Akedo (?:Leaf|Leaves)\.$/);
		if (dyn) return '利夫拥有' + dyn[1] + '片阿凯多之叶。';
		// 拼接串："BACK: B" / "TOGGLE ALL: X" / "AREA: 3/8" —— 只翻冒号前面的标签
		var m = s.match(/^([^:]{2,40}):\s*(.+)$/);
		if (m) {
			hit = lookup(m[1]);
			if (hit !== undefined) return hit + '：' + m[2];
			hit = lookup(m[1].trim());
			if (hit !== undefined) return hit + '：' + m[2];
		}
		return s;
	}

	/* --- 1) 显示层文本翻译 ------------------------------------- */
	var SFT = self.SpriteFontText;
	if (SFT && SFT.prototype && !SFT.prototype.__isleCN) {
		var origSetText = SFT.prototype.SetText;
		SFT.prototype.SetText = function (t) {
			var out = translate(t);
			// 只要最终文本含中文就按字换行（不能只看“是否被翻译过”：
			// 游戏自己产生的中文、或已经被翻译过的串，同样需要 cjk）
			if (hasCJK(out)) {
				try { this.SetWordWrapMode('cjk'); } catch (e) { /* ignore */ }
			}
			return origSetText.call(this, out);
		};
		SFT.prototype.__isleCN = true;
	}

	/* --- 2) 字形集扩展：任何来源的字符集都补上中文字形 ------- */
	var P = self.C3 && self.C3.Plugins && self.C3.Plugins.Spritefont2;
	if (P && P.Type && P.Type.prototype && !P.Type.prototype.__isleCN) {
		var origUpdate = P.Type.prototype.UpdateSettings;
		P.Type.prototype.UpdateSettings = function (cw, ch, charset, sd) {
			try {
				grabRuntime(this);
				var tname = (this.GetName ? this.GetName() : '');
				// 字格尺寸与字符集都按类型强制为“与字形表一致”的值：
				// 运行期新建的实例可能带来引擎默认值（16x16 / 另一套字符集），会直接让字形错位
				if (TYPE_CELL[tname]) { cw = TYPE_CELL[tname][0]; ch = TYPE_CELL[tname][1]; }
				if (TYPE_CHARSET[tname] && (!charset || charset.indexOf('\u4e00') < 0)) {
					charset = TYPE_CHARSET[tname];
				} else if (typeof charset === 'string' && charset.indexOf('\u4e00') < 0) {
					var mapped = CHARSET_MAP[charset];
					charset = (mapped !== undefined) ? mapped : (charset + CN_CHARS);
				}
			} catch (e) { /* ignore */ }
			return origUpdate.call(this, cw, ch, charset, sd);
		};
		P.Type.prototype.__isleCN = true;
	}

	/* --- 2.5) 说明框下移（显示层，按实例） ------------------- */
	var RTRT = null, GAP_TYPES = null;
	function grabRuntime(x) {
		try { if (!RTRT && x && x.GetRuntime) RTRT = x.GetRuntime(); } catch (e) { /* ignore */ }
		try { if (!RTRT && x && x._runtime) RTRT = x._runtime; } catch (e) { /* ignore */ }
	}
	function applyGap(inst) {
		try {
			var oc = inst.GetObjectClass && inst.GetObjectClass();
			var tn = (oc && oc.GetName) ? oc.GetName() : '';
			if (!TYPE_CELL[tn]) return;                  // 只管菜单/说明类
			var wi = inst.GetWorldInfo && inst.GetWorldInfo();
			if (!wi) return
			var y = wi.GetY();
			// 首次见到、或游戏把它移动了很大一段（重新摆版面）时，重新记基准；
			// 小幅变化视为我们自己推的那 3px，保持基准不变。
			if (inst.__cnY0 === undefined || Math.abs(y - (inst.__cnY0 + GAP_NUDGE)) > 20)
				inst.__cnY0 = y;
			try { if (wi.SetY === undefined && wi.SetY === null) return; } catch (e) { /* ignore */ }
			var want = inst.__cnY0 + GAP_NUDGE;
			if (Math.abs(wi.GetY() - want) > 0.01) wi.SetY(want);
			if (!inst.__cnGapTimer) {                     // 游戏可能稍后才摆位置，再守 4 秒
				inst.__cnGapTimer = 1; var n = 0;
				var iv = setInterval(function () {
					try {
						var w = inst.GetWorldInfo && inst.GetWorldInfo();
						if (!w) { clearInterval(iv); return; }
						if (Math.abs(w.GetY() - (inst.__cnY0 + GAP_NUDGE)) > 0.01)
							w.SetY(inst.__cnY0 + GAP_NUDGE);
					} catch (e) { /* ignore */ }
					if (++n > 16) clearInterval(iv);
				}, 250);
			}
		} catch (e) { /* ignore */ }
	}

	function gapSweep() {
		// 每 500ms 扫一遍“名字/说明”这类对象：找出“下面那个框的顶紧贴着上一个框的底”
		// 的实例对，只把下面那个往下推 GAP_NUDGE 像素（显示层，不动游戏逻辑）
		try {
			if (!RTRT) return;
			for (var i = 0; i < GAPPY.length; i++) {
				var oc = RTRT.GetObjectClassByName(GAPPY[i]);
				if (!oc || !oc.GetInstances) continue;
				var arr = oc.GetInstances() || [], boxes = [];
				for (var j = 0; j < arr.length; j++) {
					try {
						var w = arr[j].GetWorldInfo();
						if (w && (!w.IsVisible || w.IsVisible())) boxes.push([arr[j], w]);
					} catch (e) { /* ignore */ }
				}
				for (var a = 0; a < boxes.length; a++) {
					for (var b = 0; b < boxes.length; b++) {
						if (a === b) continue;
						var wa = boxes[a][1], wb = boxes[b][1];
						var flush = Math.abs(wb.GetY() - (wa.GetY() + wa.GetHeight())) <= 1;
						var overlap = wb.GetX() < wa.GetX() + wa.GetWidth()
							&& wa.GetX() < wb.GetX() + wb.GetWidth();
						if (flush && overlap) applyGap(boxes[b][0]);
					}
				}
			}
		} catch (e) { /* ignore */ }
	}
	function startSweep() {
		if (!RTRT || startSweep.__on) return;
		startSweep.__on = 1;
		if (GAPPY.length) setInterval(gapSweep, 500);
	}

	if (P && P.Instance && P.Instance.prototype && !P.Instance.prototype.__isleGap) {
		var origSet2 = P.Instance.prototype._SetText;
		P.Instance.prototype._SetText = function (t) {
			var r = origSet2.call(this, t);
			grabRuntime(this);
			startSweep();
			gapSweep();          // 立刻扫一次（只推“紧贴着上一行”的那个框）
			return r;
		};
		P.Instance.prototype.__isleGap = true;
	}

	/* --- 3) 实例设置：字距 + 中文强制按字换行 ---------------- */
	if (P && P.Instance && P.Instance.prototype && !P.Instance.prototype.__isleCN) {
		var origUpd = P.Instance.prototype._UpdateSettings;
		P.Instance.prototype._UpdateSettings = function () {
			var out;
			grabRuntime(this);
			try {
				var oc = this.GetObjectClass && this.GetObjectClass();
				var tn = (oc && oc.GetName) ? oc.GetName() : '';
				if (TYPE_SPACING[tn] && this._spriteFontText && this._spriteFontText.SetSpacing) {
					this._spriteFontText.SetSpacing(TYPE_SPACING[tn]);
				}
			} catch (e) { /* ignore */ }
			out = origUpd.call(this);
			try {
				// 插件会用实例属性把 wrapMode 重置回 'word'；中文没有空格，
				// 不强制成 'cjk' 的话长句会整行溢出文本框
				// 实例里存的是原文（英文），所以要看“翻译之后”有没有中文
				if (typeof this._text === 'string' && hasCJK(translate(this._text))
						&& this._spriteFontText) {
					this._spriteFontText.SetWordWrapMode('cjk');
				}
			} catch (e) { /* ignore */ }
			return out;
		};
		P.Instance.prototype.__isleCN = true;
	}
})();
