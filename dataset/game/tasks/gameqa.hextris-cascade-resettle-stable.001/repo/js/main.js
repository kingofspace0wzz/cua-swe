function scaleCanvas() {
	canvas.width = $(window).width();
	canvas.height = $(window).height();

	if (canvas.height > canvas.width) {
		settings.scale = (canvas.width / 800) * settings.baseScale;
	} else {
		settings.scale = (canvas.height / 800) * settings.baseScale;
	}

	trueCanvas = {
		width: canvas.width,
		height: canvas.height
	};

	if (window.devicePixelRatio) {
		var cw = $("#canvas").attr('width');
		var ch = $("#canvas").attr('height');

		$("#canvas").attr('width', cw * window.devicePixelRatio);
		$("#canvas").attr('height', ch * window.devicePixelRatio);
		$("#canvas").css('width', cw);
		$("#canvas").css('height', ch);

		trueCanvas = {
			width: cw,
			height: ch
		};

		ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
	}
	if (typeof setBottomContainer === "function" && $("#buttonCont").length) {
		setBottomContainer();
	}
	if (typeof set_score_pos === "function" && $("#container").length && $("#highScoreInGameText").length) {
		set_score_pos();
	}
}

function setBottomContainer() {
	var button = $("#buttonCont");
	if (!button.length) {
		return;
	}
	var buttonOffset = button.offset();
	if (!buttonOffset || buttonOffset.top == null) {
		return;
	}
	var playOffset = trueCanvas.height / 2 + 100 * settings.scale;
	var delta = buttonOffset.top - playOffset - 29;
	if (delta < 0) {
		$("#bottomContainer").css("margin-bottom", "-" + Math.abs(delta) + "px");
	}
}

function set_score_pos() {
	var container = $("#container");
	var buttonCont = $("#buttonCont");
	var igt = $("#highScoreInGameText");
	if (!container.length || !buttonCont.length || !igt.length || !container.offset() || !buttonCont.offset() || !igt[0]) {
		return;
	}

	container.css('margin-top', '0');
	var middle_of_container = (container.height() / 2 + container.offset().top);
	var top_of_bottom_container = buttonCont.offset().top;
	var igt_bottom = igt.offset().top + igt[0].offsetHeight;
	var target_midpoint = (top_of_bottom_container + igt_bottom) / 2;
	var diff = (target_midpoint - middle_of_container);
	container.css("margin-top", diff + "px");
}

function toggleDevTools() {
	$('#devtools').toggle();
}

function resumeGame() {
	gameState = 1;
	hideUIElements();
	$('#pauseBtn').show();
	$('#restartBtn').hide();
	importing = 0;
	startTime = Date.now();
	setTimeout(function() {
		if ((gameState == 1 || gameState == 2) && !$('#helpScreen').is(':visible')) {
			$('#openSideBar').fadeOut(150, "linear");
		}
	}, 7000);

	checkVisualElements(0);
}

function checkVisualElements(arg) {
	if (arg && $('#openSideBar').is(":visible")) $('#openSideBar').fadeOut(150, "linear");
	if (!$('#pauseBtn').is(':visible')) $('#pauseBtn').fadeIn(150, "linear");
	$('#fork-ribbon').fadeOut(150);
	if (!$('#restartBtn').is(':visible')) $('#restartBtn').fadeOut(150, "linear");
	if ($('#buttonCont').is(':visible')) $('#buttonCont').fadeOut(150, "linear");
}

function hideUIElements() {
	$('#pauseBtn').hide();
	$('#restartBtn').hide();
	$('#startBtn').hide();
}

function init(b) {
	if(settings.ending_block && b == 1){return;}
	if (b) {
		$("#pauseBtn").attr('src',"./images/btn_pause.svg");
		if ($('#helpScreen').is(":visible")) {
			$('#helpScreen').fadeOut(150, "linear");
		}

		setTimeout(function() {
            if (gameState == 1) {
			    $('#openSideBar').fadeOut(150, "linear");
            }
			infobuttonfading = false;
		}, 7000);
		clearSaveState();
		checkVisualElements(1);
	}
	if (highscores.length === 0 ){
		$("#currentHighScore").text(0);
	}
	else {
		$("#currentHighScore").text(highscores[0])
	}
	infobuttonfading = true;
	$("#pauseBtn").attr('src',"./images/btn_pause.svg");
	hideUIElements();
	var saveState = {};
	document.getElementById("canvas").className = "";
	history = {};
	importedHistory = undefined;
	importing = 0;
	score = saveState.score || 0;
	prevScore = 0;
	spawnLane = 0;
	op = 0;
	tweetblock=false;
	scoreOpacity = 0;
	gameState = 1;
	$("#restartBtn").hide();
	$("#pauseBtn").show();
	if (saveState.hex !== undefined) gameState = 1;

	settings.blockHeight = settings.baseBlockHeight * settings.scale;
	settings.hexWidth = settings.baseHexWidth * settings.scale;
	MainHex = saveState.hex || new Hex(settings.hexWidth);
	// Suppress the intro tutorial overlay so auto-start gameplay is visible.
	MainHex.playThrough = 1;
	MainHex.sideLength = settings.hexWidth;

	var i;
	var block;
	if (saveState.blocks) {
		saveState.blocks.map(function(o) {
			if (rgbToHex[o.color]) {
				o.color = rgbToHex[o.color];
			}
		});

		for (i = 0; i < saveState.blocks.length; i++) {
			block = saveState.blocks[i];
			blocks.push(block);
		}
	} else {
		blocks = [];
	}

	gdx = saveState.gdx || 0;
	gdy = saveState.gdy || 0;
	comboTime = saveState.comboTime || 0;

	for (i = 0; i < MainHex.blocks.length; i++) {
		for (var j = 0; j < MainHex.blocks[i].length; j++) {
			MainHex.blocks[i][j].height = settings.blockHeight;
			MainHex.blocks[i][j].settled = 0;
		}
	}

	MainHex.blocks.map(function(i) {
		i.map(function(o) {
			if (rgbToHex[o.color]) {
				o.color = rgbToHex[o.color];
			}
		});
	});

	MainHex.y = -100;

	startTime = Date.now();
	waveone = saveState.wavegen || new waveGen(MainHex);

	MainHex.texts = []; //clear texts
	MainHex.delay = 15;
	hideText();
}

function addNewBlock(blocklane, color, iter, distFromHex, settled) { //last two are optional parameters
	iter *= settings.speedModifier;
	if (!history[MainHex.ct]) {
		history[MainHex.ct] = {};
	}

	history[MainHex.ct].block = {
		blocklane: blocklane,
		color: color,
		iter: iter
	};

	if (distFromHex) {
		history[MainHex.ct].distFromHex = distFromHex;
	}
	if (settled) {
		blockHist[MainHex.ct].settled = settled;
	}
	blocks.push(new Block(blocklane, color, iter, distFromHex, settled));
}

function exportHistory() {
	$('#devtoolsText').html(JSON.stringify(history));
	toggleDevTools();
}

function setStartScreen() {
	// Remove any stale DOM overlays introduced by upstream assets/scripts.
	$("#overlay,.overlay,#helpScreen,#gameoverscreen,#container,#buttonCont,#socialShare,#restart,#pauseBtn,#restartBtn,#openSideBar").remove();

	if (typeof window.__hextrisClearTerminal === "function") {
		window.__hextrisClearTerminal();
	}
	clearSaveState();
	importing = 1;

	$('#startBtn').hide();
	$('#pauseBtn').hide();
	$('#restartBtn').hide();
	hideText();
	$('.overlay, #helpScreen, #gameoverscreen, #container, #buttonCont, #socialShare, #restart').hide();
	$('#pauseBtn, #restartBtn, #openSideBar').hide();
	$('.helpText').hide();
	$('#overlay').hide();

	init(1);
	checkVisualElements(0);
	requestAnimFrame(animLoop);
}

var spd = 1;

function animLoop() {
	switch (gameState) {
	case 1:
		requestAnimFrame(animLoop);
		render();
		var now = Date.now();
		var dt = (now - lastTime)/16.666 * rush;
		if (spd > 1) {
			dt *= spd;
		}

		if(gameState == 1 ){
			if(!MainHex.delay) {
				update(dt);
			}
			else{
				MainHex.delay--;
			}
		}

		lastTime = now;

		if (checkGameOver() && !importing) {
			// Auto-reset and restart immediately on death.
			$("#gameoverscreen").hide();
			$("#buttonCont").hide();
			$("#container").hide();
			$("#socialShare").hide();
			$("#restart").hide();
			canRestart = 1;
			clearSaveState();
			init(1);
			importing = 0;
		}
		break;

	case 0:
		requestAnimFrame(animLoop);
		render();
		break;

	case -1:
		gameState = 1;
		requestAnimFrame(animLoop);
		render();
		break;

	case 2:
		var now = Date.now();
		var dt = (now - lastTime)/16.666 * rush;
		requestAnimFrame(animLoop);
		update(dt);
		render();
		lastTime = now;
		break;

	case 3:
		requestAnimFrame(animLoop);
		fadeOutObjectsOnScreen();
		render();
		break;

	case 4:
		setTimeout(function() {
			initialize(1);
		}, 1);
		render();
		return;

	default:
		initialize();
		setStartScreen();
		break;
	}

	if (!(gameState == 1 || gameState == 2)) {
		lastTime = Date.now();
	}
}

function enableRestart() {
	canRestart = 1;
}

function isInfringing(hex) {
	for (var i = 0; i < hex.sides; i++) {
		var subTotal = 0;
		for (var j = 0; j < hex.blocks[i].length; j++) {
			subTotal += hex.blocks[i][j].deleted;
		}

		if (hex.blocks[i].length - subTotal > settings.rows) {
			return true;
		}
	}
	return false;
}

function checkGameOver() {
	if (!window.__hextrisSetTerminal) {
		window.__hextrisSetTerminal = function (outcome, reason) {
			window.__hextrisTerminal = window.__hextrisTerminal || {
				isTerminal: false,
				outcome: null,
				reason: null,
				ts: 0,
				score: null,
				level: null,
				difficulty: null,
				distance: null,
				environment: null,
			};
			if (window.__hextrisTerminal.isTerminal) {
				return;
			}
			window.__hextrisTerminal.isTerminal = true;
			window.__hextrisTerminal.outcome = outcome || "fail";
			window.__hextrisTerminal.reason = reason || "game_over";
			window.__hextrisTerminal.ts = Date.now();
			window.__hextrisTerminal.score = typeof score === "number" && isFinite(score) ? Math.floor(score) : null;
			window.__hextrisTerminal.level = typeof window.initialDifficultyFromQuery === "number" && isFinite(window.initialDifficultyFromQuery) ? Math.floor(window.initialDifficultyFromQuery) : null;
			window.__hextrisTerminal.difficulty = window.waveone && typeof window.waveone.difficulty === "number" && isFinite(window.waveone.difficulty) ? window.waveone.difficulty : null;
			window.__hextrisTerminal.distance = window.MainHex && typeof window.MainHex.ct === "number" && isFinite(window.MainHex.ct) ? Math.floor(window.MainHex.ct) : null;
			var settledBlocks = 0;
			var highestColumn = 0;
			if (window.MainHex && Array.isArray(window.MainHex.blocks)) {
				for (var side = 0; side < window.MainHex.blocks.length; side++) {
					settledBlocks += window.MainHex.blocks[side].length;
					highestColumn = Math.max(highestColumn, window.MainHex.blocks[side].length);
				}
			}
			window.__hextrisTerminal.environment = {
				settled_blocks: settledBlocks,
				highest_column_height: highestColumn,
				active_blocks: Array.isArray(window.blocks) ? window.blocks.length : 0,
			};
		};
	}

	if (!window.__hextrisGetTerminal) {
		window.__hextrisGetTerminal = function () {
			if (!window.__hextrisTerminal) {
				return {
					isTerminal: false,
					outcome: null,
					reason: null,
				};
			}

			if (!window.__hextrisTerminal.isTerminal) {
				return {
					isTerminal: false,
					outcome: null,
					reason: null,
				};
			}

			return {
				isTerminal: true,
				outcome: window.__hextrisTerminal.outcome,
				reason: window.__hextrisTerminal.reason,
			};
			};
	}

	if (!window.__hextrisClearTerminal) {
		window.__hextrisClearTerminal = function () {
			if (!window.__hextrisTerminal) {
				window.__hextrisTerminal = {
					isTerminal: false,
					outcome: null,
					reason: null,
					ts: 0,
					score: null,
					level: null,
					difficulty: null,
					distance: null,
					environment: null,
				};
			}

			window.__hextrisTerminal.isTerminal = false;
			window.__hextrisTerminal.outcome = null;
			window.__hextrisTerminal.reason = null;
			window.__hextrisTerminal.ts = 0;
			window.__hextrisTerminal.score = null;
			window.__hextrisTerminal.level = null;
			window.__hextrisTerminal.difficulty = null;
			window.__hextrisTerminal.distance = null;
			window.__hextrisTerminal.environment = null;
		};
	}

	for (var i = 0; i < MainHex.sides; i++) {
		if (isInfringing(MainHex)) {
			window.__hextrisSetTerminal("fail", "game_over");
			if (highscores.indexOf(score) == -1) {
				highscores.push(score);
			}
			writeHighScores();
			return true;
		}
	}
	return false;
}

function showHelp() {
	return;
}

(function(){
	// Disabled external bootstrap script to avoid injected overlays/loading UI.
})()
