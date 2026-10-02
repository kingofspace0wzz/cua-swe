(function (window) {

    //add prototype to window
    window.storageManager = new StorageManager();

	//main prototype
	function StorageManager() {
        //prototype functions
        this.init = function(){
            //initiate object variables
            this.prefix = "br_"; //used for distinguishing local storage
            this.tempName = ''; //initialize temp name
        };
        this.tick = function (delta) {  };
        this.trimLevel = function(expandedLevel){
            var mapRegex = /<map[^>]*>((.|[\n\r])*)<\/map>/im; //http://stackoverflow.com/a/3642850/2510368
            var tipRegex = /<tip[^>]*>((.|[\n\r])*)<\/tip>/im;
            this.levelString = mapRegex.exec(expandedLevel)[1].trim();
            this.tipString = tipRegex.exec(expandedLevel)[1].trim();
        };
        this.trimLocalLevel = function(key, hasFileOrigin){
            var rawLevelString = "";
            if (hasFileOrigin == true) rawLevelString = window.Game.assetManager.preload.getResult(key+"").toString();
            else rawLevelString = this.getFromLocalStorage(this.prefix+key); //get storage by key
            this.trimLevel(rawLevelString);
        };
        this.expandLevel = function(){
            return "<map>\r\n"+this.levelString+"\r\n</map>\r\n<tip>\r\n"+this.tipString+"\r\n</tip>";
        };
        this.saveToLocalStorage = function(index){
            if (index == null){	index = 1; while (localStorage.getItem(this.prefix + index) !== null){ index++; }}
            localStorage.setItem(this.prefix + index,this.expandLevel());
            return index;
        };
        this.setLevelString = function(levelString){ this.levelString = levelString; };
        this.getFromLocalStorage = function(key){ return localStorage.getItem(key); };
        this.getLocalStorageLength = function(){ return localStorage.length; };
        this.getLocalStorageKey = function(index) { return localStorage.key(index); };
        this.removeFromLocalStorage = function(key){ localStorage.removeItem(this.prefix + key); };
        this.clearLocalStorage = function() { localStorage.clear(); }

        this.getPortalStorageKey = function(name) {
            return this.prefix + "portal_" + name;
        };

        this.saveLevelToPortal = function(name, levelMap) {
            if (this.checkDailyLimit('upload')){
                window.Game.dialog.openDialogWindow("shareCode"); //prompt uploading window
                localStorage.setItem(this.getPortalStorageKey(name), levelMap);
                window.Game.dialog.createInputDialog(); //prevent null values
                window.Game.dialog.input.value = "#"+name;
                window.Game.dialog.openDialogWindow("uploadSuccess");
            }
            else window.Game.dialog.openDialogWindow("errorLimit"); //upload error
        };

        this.loadLevelFromPortal = function(name){
            if (this.checkDailyLimit('download')) {
                if (window.storageManager.tempName != name) { //prevent spamming download
                    window.Game.dialog.openDialogWindow("downloading"); //prompt downloading window
                    var levelMap = localStorage.getItem(window.storageManager.getPortalStorageKey(name));
                    if (levelMap != null) {
                        window.Game.theme.setTheme('editLand');
                        if (levelMap.indexOf('<map>') < 0) levelMap = LZString.decompressFromUTF16(levelMap);

                        if (levelMap != null) {
                            // update level data
                            window.storageManager.trimLevel(levelMap);
                            window.storageManager.tempName = name; // used for telling the database that the level was completed
                            window.Game.levelMap.createMapFromString(window.storageManager.levelString);
                            window.Game.levelMap.renderMap(); //render 2d array and cache it
                            window.Game.setView(2,3); //fake previous view to level editor
                            window.Game.levelEditor.updateUI(1);
                            window.Game.player.respawn();
                            window.Game.interface.build();
                            window.Game.pauseGame();
                            window.Game.dialog.openDialogWindow("downloadSuccess"); //download success
                        }
                        else window.Game.dialog.openDialogWindow("error404"); //download error 404
                    }
                    else window.Game.dialog.openDialogWindow("error404"); //download error 404
                }
            }
            else window.Game.dialog.openDialogWindow("errorLimit"); //download error
        };

        this.checkCompleted = function() {
            if (window.storageManager.tempName.length > 0){
                window.storageManager.tempName = ''; // reset name to prevent database completion
            }
        };

        this.addVoteToLevel = function(name, vote) {
            return;
        };
        
        this.saveLevelToFile = function(){
            window.Game.levelEditor.saveCurrentLevel();
            var blob = new Blob([this.expandLevel()], { type: "text/plain;charset=utf-8;" });
            saveAs(blob, (Math.floor(Math.random()*16777215).toString(16)).toUpperCase() + ".txt");
        }
        this.loadLevelFromFile = function(){
            var input = document.createElement("input");
            input.setAttribute('type', 'file');
            input.setAttribute('id', 'theFile');
            input.addEventListener('change', handleFileSelect, false);
            function performClick() {
                var evt = document.createEvent("MouseEvents");
                evt.initEvent("click", true, false);
                input.dispatchEvent(evt);
            }
            function handleFileSelect(evt) {
                var files = evt.target.files;
                f = files[0];
                var reader = new FileReader();
                reader.onload = (function(theFile) {
                    return function(e) {
                        levelMap = e.target.result;
                        //console.log(levelMap);
                        window.storageManager.trimLevel(levelMap);
                        window.Game.levelMap.createMapFromString(window.storageManager.levelString);
                        window.Game.levelMap.renderMap(); //render 2d array and cache it
                        window.Game.setView(2,3); //fake previous view to level editor
                        window.Game.levelEditor.updateUI(1);
                        window.Game.player.respawn();
                        window.Game.interface.build();
                        window.Game.pauseGame();
                        window.Game.dialog.openDialogWindow("downloadSuccess"); //download success
                    };
                })(f);
                reader.readAsText(f);
            }
            performClick();
        }
        this.createMapCanvas = function(levelMap){
            var canvas = document.createElement("CANVAS");
            var ctx = canvas.getContext("2d");
            canvas.width = levelMap.getCols();
            canvas.height = levelMap.getRows();
            ctx.fillStyle = "transparent"; //draw background
            ctx.fillRect(0,0,canvas.width,canvas.height);

            //draw each tile
            var t = 0; //tile type (255 options possible)
            for (var row=0; row < levelMap.map.length; row++){
                for (var col=0; col < levelMap.map[row].length; col++){
                    t = parseInt(('0'+levelMap.map[row][col].type).slice(-2));
                    t = parseInt((t * 255) / 16);
                    if (t > 0){
                        ctx.fillStyle = window.lb.rgbToHex("rgb("+t+", "+0+", "+t+");");
                        ctx.fillRect(col,row,1,1);
                    }
                }
            }
            return canvas;
        };
        this.exportMapToPNG = function(levelMap, fileName){
            var canvas = this.createMapCanvas(levelMap);

            fileName = fileName != null ? fileName : "boxel-level";
            var MIME_TYPE = "image/png"; //set type
            var imgURL = canvas.toDataURL(MIME_TYPE);

            var dlLink = document.createElement('a'); //temporary link
            dlLink.download = fileName; //temporary name
            dlLink.href = imgURL;
            dlLink.dataset.downloadurl = [MIME_TYPE, dlLink.download, dlLink.href].join(':');

            document.body.appendChild(dlLink);
            dlLink.click();
            document.body.removeChild(dlLink);
        };
        this.exportMapToPNGImage = function(levelMapString, fileName){
            window.storageManager.trimLevel(levelMapString);
            window.Game.levelMap.createMapFromString(window.storageManager.levelString);
            var canvas = this.createMapCanvas(window.Game.levelMap);

            fileName = fileName != null ? fileName : "boxel-level";
            var MIME_TYPE = "image/png"; //set type
            var imgURL = canvas.toDataURL(MIME_TYPE);
            return imgURL;
        };
        this.saveLevelScore = function(index, score){
            localStorage.setItem("level_" + index + "_score", score);
            return index;
        };
        this.getLevelScore = function(level){ 
            var key = localStorage.getItem("level_"+level+"_score");
            return key !== null ? key : "00:00"; 
        };
        this.storeVolume = function(volume){
            localStorage.setItem("volume", volume);
        };
        this.getVolume = function(){
            var volume = localStorage.getItem("volume");
            if (volume == null) localStorage.setItem("volume", 0); //set 0% volume if empty
            return volume;
        };
        this.getUserToken = function(){
            var userToken = localStorage.getItem("user_token");
            if (userToken == null) {
                var userToken = '';
                var randomPool = new Uint8Array(32);
                crypto.getRandomValues(randomPool);
                for (var i = 0; i < randomPool.length; ++i) userToken += randomPool[i].toString(16);
                localStorage.setItem("user_token", userToken);
            }
            return userToken;
        };
        this.toggleVolume = function(){
            var volume = localStorage.getItem("volume");
            localStorage.setItem("volume", volume != 0 ? 0 : 1);
            window.Game.syncLocalVolume();
        };
        this.getFullscreenValue = function(){
            var fullscreen = localStorage.getItem("fullscreen");
            if (fullscreen == null) localStorage.setItem("fullscreen", 0); //default 0 if empty
            return fullscreen;
        }
        this.toggleFullscreenValue = function(){
            var fullscreen = localStorage.getItem("fullscreen");
            localStorage.setItem("fullscreen", fullscreen != 0 ? 0 : 1);
        };
        this.getFastModeValue = function(){
            var fastMode = localStorage.getItem("fastmode");
            if (fastMode == null) localStorage.setItem("fastmode", 0); //default 0 if empty
            return fastMode;
        }
        this.toggleFastModeValue = function(){
            var fastMode = localStorage.getItem("fastmode");
            localStorage.setItem("fastmode", fastMode != 0 ? 0 : 1);
        };
        this.getTotalScoreString = function(raw){
            var score = 0;
            var localScore = "";
            var i = 1;
            while (localScore != "00:00"){
                localScore = window.storageManager.getLevelScore(i);
                score += parseInt(localScore.replace(':',''));
                i++;
            }
            score += "";
            if (raw) score = score.splice(score.length - 2, 0, "."); //splice prototype from LunchBox.js;
            else score = Number(score).toLocaleString();
            return score
        };

        this.checkDailyLimit = function(limitType, check){
            var date = Date.now();
            var max_daily_uploads = 5;
            var max_daily_downloads = 10;
            var limit = false;
            var key = (limitType == 'upload') ? 'daily_uploads' : 'daily_downloads';

            //reset dates if purchased, null or a new 1 hours, reset start_date, daily_uploads, and daily downloads
            if (this.hasLicense() || 
                localStorage.getItem('start_date') == null || 
                localStorage.getItem('daily_uploads') == null ||
                localStorage.getItem('daily_downloads') == null ||
                date >= parseInt(localStorage.getItem('start_date')) + (1000 * 60 * 60 * 24)) {
                    localStorage.setItem('start_date', date);
                    localStorage.setItem('daily_uploads', max_daily_uploads);
                    localStorage.setItem('daily_downloads', max_daily_downloads);
            }
            
            //check if limitType is exceeded
            if (check != true) localStorage.setItem(key, localStorage.getItem(key) - 1);
            if (localStorage.getItem(key) >= 0) limit = true;
            return limit;
        };

        this.setLicense = function(license){
            localStorage.setItem('license', license);
        };

        this.hasLicense = function(){
            var hasLicense = localStorage.getItem('license') == 'boxel_rebound_pro';
            localStorage.setItem("skin_id_0", 1); // enable skin 1 by default
            if (hasLicense) this.activateSkins();
            return hasLicense;
        };

        this.setSkinId = function(skinId){
            localStorage.setItem('skin', skinId);
        };

        this.getSkinId = function(){
            var skinId = localStorage.getItem('skin');
            if (skinId == null) { skinId = 0; this.setSkinId(skinId); }
            return parseInt(skinId);
        };

        this.activateSkin = function(i) {
            localStorage.setItem("skin_id_" + i, 1);
        };

        this.activateSkins = function() {
            for (var i = 1; i < 8; i++) {
                this.activateSkin(i);
            }
        };

        this.skinIsActive = function(i) {
            return localStorage.getItem('skin_id_' + i) == 1;
        };

        this.uploadLocalStorageToChromeStorage = function(clear){
            return;
        };

        this.downloadChromeStorageToLocalStorage = function(clear){
            return;
        };

        this.checkChromeStorage = function(){
            return;
        };

        this.getMaxLevels = function(){
            var maxLevels = localStorage.getItem('max_levels');
            if (maxLevels == null) {
                maxLevels = 3;
                localStorage.setItem('max_levels', maxLevels);
            }
            return maxLevels;
        };

        this.unlockLevelSkin = function(level) {
            if (level == 5) localStorage.setItem('skin_id_2', 1); // Circle
            else if (level == 10) localStorage.setItem('skin_id_7', 1); // Bird
            else if (level == 20) localStorage.setItem('skin_id_4', 1); // Cat
            else if (level == 30) localStorage.setItem('skin_id_5', 1); // Dog
            else if (level == 40) localStorage.setItem('skin_id_6', 1); // Mouse
            else if (level == 50) localStorage.setItem('skin_id_1', 1); // Tri-force
        };

        //initiate variables
        this.init();
	}
}(window));
