
(function (window) {

    //extend & promote createjs.Container functions to window
    createjs.extend(LevelMap, createjs.Container);
    window.LevelMap = createjs.promote(LevelMap, "Container");

    //main prototype
	function LevelMap() {
        //prototype functions
	    this.init = function(){
            this.Container_constructor();
            this.box = Math.floor(window.Game.box12);
            this.map = [];
            this.mapHistory = [];
            this.historyIndex = 0;
            this.motionTime = 0;
            this.cameraProgress = 0;
            this.movingSupports = [];
            this.mapView = null;
            this.guideView = null;
            this.guideRemaining = 0;
        };

        //update
        this.tick = function (delta) {
            this.motionTime += delta;
            var target = window.Game.player.xPos;
            this.cameraProgress += (target-this.cameraProgress)*Math.min(1,delta/180);
            this.x = -this.cameraProgress;
            for (var i=0; i<this.movingSupports.length; i++){
                this.movingSupports[i].update(this.motionTime);
            }
            if (this.guideView != null){
                this.guideRemaining -= delta;
                if (this.guideRemaining <= 0){
                    if (this.guideView.parent != null) this.guideView.parent.removeChild(this.guideView);
                    this.guideView = null;
                }
                else {
                    this.guideView.alpha = 0.24*Math.min(1,this.guideRemaining/900);
                }
            }
        };

        this.createMapFromString = function(mapString){
            this.map = []; //create empty map
            var rows = window.lb.occurrences(mapString,"\n", false)+1;
            var cols = Math.floor(mapString.substring(0,mapString.indexOf('\n')).length / 2); //ignores hidden \r
            mapString = mapString.replace(/(\r\n|\n|\r)/gm,"");
            for (var row=0; row < rows; row++){
                this.map[row] = [];
                for (var col=0; col < cols; col++){
                    var i = col+(row*(cols));
                    this.map[row][col] = new this.tile(parseInt(mapString.substring(i*2,(i*2)+2)));
                }
            }
        }

        this.createEmptyMap = function(cols, rows){
            this.map = [];
            for (var row=0; row < rows; row++){
                this.map[row] = [];
                for (var col=0; col < cols; col++){
                    this.map[row][col] = new this.tile(0);
                }
            }
        };

        this.tile = function(type){
            this.type = type;
            this.isSolid = window.tiles.isSolid(type);
        };

        this.setTile = function(col, row, type, lockCols, lockRows){
            var rows = this.map.length;
            var cols = (rows > 0) ? this.map[0].length : 0;
            var nRow = row < 0 ? Math.abs(row) : 0;
            var nCol = col < 0 ? Math.abs(col) : 0;
            var nRowCount = nRow;
            var nColCount = nCol;
            if (lockCols == null) lockCols = false;
            if (lockRows == null) lockRows = true;
            var success = true;

            //prevent array row mutation if specified
            if (lockRows != true){
                while (nRow > 0){ //check if row < 0
                    this.map.unshift([]);
                    for (var c=0; c < cols; c++){ this.map[0][c] = new this.tile(0); }
                    nRow--;
                }
                while (row > (rows-1)){ //check if row > current rows
                    this.map[rows] = [];
                    for (var c=0; c < cols; c++){ this.map[rows][c] = new this.tile(0); }
                    rows++;
                }
            }
            //prevent array column mutation if specified
            if (lockCols != true){
                while (nCol > 0){ //check if col < 0
                    for (var r=0; r < rows+nRowCount; r++){
                        try { if (nRow <= 0 && row < rows) this.map[r].unshift(new this.tile(0)); }
                        catch (e) { if (e instanceof TypeError) { success = false; }}
                    }
                    nCol--;
                }
                while (col > (cols-1)){ //check if col > current columns
                    for (var r=0; r < rows+nRowCount; r++){
                        try { if (nRow <= 0 && row < rows) this.map[r][cols] = new this.tile(0); }
                        catch (e) { if (e instanceof TypeError) { success = false; }}
                    }
                    cols++;
                }
            }
            //set the array property type if within the 'lock' rules
            try {
                var tempMap = this.map[row+nRowCount+(lockRows && row<0 ? -1:0)][col+nColCount+(lockCols && col<0 ? -1:0)];
                tempMap.type = type;
                tempMap.isSolid = window.tiles.isSolid(type);
            }
            catch (e) { if (e instanceof TypeError) { success = false; }}
            return success;
        };

        this.getTile = function(x, y){
            var tile;
            if (x < this.x || y < this.y || x >+ this.getWidth() || y >= this.y+this.getHeight()) tile = null;
            else tile = this.map[this.getTileRow(y)][this.getTileCol(x)];
            return tile;
        };

        this.getTileRow = function(y){ return Math.floor((y-this.y)/this.box); };
        this.getTileCol = function(x){ return Math.floor(x/this.box); };
        this.toString = function(toConsole){
            var aString = "";
            for (var row=0; row < this.map.length; row++){
                for (var col=0; col < this.map[row].length; col++){
                    aString += ('0'+this.map[row][col].type).slice(-2); //double digit string
                }
                if (row < this.map.length-1) aString += "\r\n"; //prevent last return & next line
            }
            if (toConsole == true) console.log(aString);
            return aString;
        };
        this.removeColumn = function(){
            var col = (((this.box * 6) - this.x)/this.box);
            if (col < 0) col = 0;
            if (col > this.getCols()) col = this.getCols();
            for (var row=0; row < this.getRows(); row++){ this.map[row].splice(col, 1); }
        };
        this.insertColumn = function(){
            var col = (((this.box * 6) - this.x)/this.box);
            if (col < 0) col = 0;
            if (col > this.getCols()) col = this.getCols();
            for (var row=0; row < this.getRows(); row++){ this.map[row].splice(col, 0, new this.tile(0)); }
        }

        this.renderMap = function(){
            this.removeAllChildren();
            var rMap = new createjs.Container(); //bg color
            this.mapView = rMap;
            this.guideView = null;
            this.guideRemaining = 0;
            var rows = this.map.length;
            var cols = this.map[0].length;
            this.movingSupports = [];
            for (var row=0; row < rows; row++){
                for (var col=0; col < cols; col++) {
                    var type = this.map[row][col].type;
                    if (type == 20){
                        var start = col;
                        while (col+1 < cols && this.map[row][col+1].type == 20) col++;
                        var support = new MovingSupport(this,row,start,col-start+1);
                        this.movingSupports.push(support);
                        rMap.addChild(support.view);
                    }
                    else if (type == 3 && row+1 < rows && this.map[row+1][col].type == 20){
                        // The support renders checkpoint beacons in its own moving frame.
                    }
                    else if (type > 0) rMap.addChild(window.tiles.drawShape(window.Game.theme.main_color4,row,col,type,true));
                }
            }
            if (this.movingSupports.length == 0) rMap.cache(0,0, cols*this.box, rows*this.box);
            this.addChild(rMap);
            this.alignFromCenter();
            for (var i=0; i<this.movingSupports.length; i++){
                this.movingSupports[i].update(this.motionTime);
            }
        };
        this.getSupport = function(id){
            for (var i=0; i<this.movingSupports.length; i++){
                if (this.movingSupports[i].id == id) return this.movingSupports[i];
            }
            return null;
        };
        this.captureGuide = function(support){
            if (support == null) return null;
            return {
                id: support.id,
                x: support.left,
                y: support.view.y,
                tiles: Math.max(1,Math.round((support.right-support.left)/this.box))
            };
        };
        this.showGuide = function(frame){
            if (this.guideView != null && this.guideView.parent != null){
                this.guideView.parent.removeChild(this.guideView);
            }
            this.guideView = null;
            this.guideRemaining = 0;
            if (frame == null || this.mapView == null) return;
            var guide = new createjs.Container();
            for (var i=0; i<frame.tiles; i++){
                guide.addChild(window.tiles.drawShape(
                    window.Game.theme.main_color4,0,i,20,true,this.box
                ));
            }
            var edge = new createjs.Shape();
            edge.graphics.beginFill(window.Game.theme.main_color1).drawRect(
                0,0,frame.tiles*this.box,Math.max(2,this.box*0.08)
            );
            guide.addChild(edge);
            guide.x = frame.x;
            guide.y = frame.y;
            guide.alpha = 0.3;
            guide.mouseEnabled = false;
            this.mapView.addChildAt(guide,0);
            this.guideView = guide;
            this.guideRemaining = 4200;
        };
        this.findSupportLanding = function(x,y1,y2,width,height){
            if (y2 < y1) return null;
            var left = x-(width/2);
            var right = x+(width/2);
            var previousBottom = y1+(height/2);
            var nextBottom = y2+(height/2);
            for (var i=0; i<this.movingSupports.length; i++){
                var support = this.movingSupports[i];
                if (right <= support.left || left >= support.right) continue;
                if (previousBottom <= support.top+6 && nextBottom >= support.top-2) return support;
            }
            return null;
        };
        this.getRows = function(){ return this.map.length; };
        this.getCols = function(){ return this.getRows() > 0 ? this.map[0].length : 0; };
        this.getWidth = function(){ return this.getCols() * this.box; };
        this.getHeight = function(){ return this.getRows() * this.box; };
        this.setBoxSize = function(boxSize){ this.box = boxSize; };
        this.shiftChildren = function(x,y){
            for (var i=0; i < this.children.length; i++){
                this.getChildAt(i).x += x;
                this.getChildAt(i).y += y;
            }
        };
        this.alignFromCenter = function(){ this.y = (window.Game.getHeight()/2)-((this.getRows()*this.box)/2); };
        this.saveMapHistory = function(resumeEditing){
            if (resumeEditing != true) {
                var tempMap = JSON.parse(JSON.stringify(this.map)); //clone
                this.mapHistory.splice(this.historyIndex+1, (this.mapHistory.length)-this.historyIndex); //trim excess lists
                this.mapHistory.push(tempMap);
                if (this.mapHistory.length > 1) this.historyIndex++;
            }
        };
        this.undoMapHistory = function(){
            if (this.mapHistory.length > 0){ //if history exists
                this.historyIndex -= this.historyIndex > 0 ? 1 : 0;
                this.map = JSON.parse(JSON.stringify(this.mapHistory[this.historyIndex]));
                this.renderMap(); //rerender
            }
        };
        this.redoMapHistory = function(){
            if (this.historyIndex < this.mapHistory.length-1){
                this.historyIndex++;
                this.map = JSON.parse(JSON.stringify(this.mapHistory[this.historyIndex]));
            }
            this.renderMap(); //rerender
        };
        this.clearMapHistory = function(){
            this.mapHistory = []; //create empty map
            this.historyIndex = 0;
        };

        //initiate prototype variables
        this.init();

        function MovingSupport(map,row,startCol,length){
            this.id = row+":"+startCol;
            this.left = startCol*map.box;
            this.right = (startCol+length)*map.box;
            this.baseY = row*map.box;
            this.top = map.y+this.baseY;
            this.checkpointCol = -1;
            for (var c=startCol; c<startCol+length; c++){
                if (row > 0 && map.map[row-1][c].type == 3){
                    this.checkpointCol = c;
                    break;
                }
            }
            this.view = new createjs.Container();
            for (var i=0; i<length; i++){
                this.view.addChild(window.tiles.drawShape(window.Game.theme.main_color4,0,i,20,true,map.box));
            }
            if (this.checkpointCol >= 0){
                var marker = window.tiles.drawShape(window.Game.theme.main_color4,-1,this.checkpointCol-startCol,3,true,map.box);
                this.view.addChild(marker);
            }
            this.view.x = this.left;
            this.view.y = this.baseY;
            this.update = function(time){
                var phase = (time%2800)/2800*Math.PI*2;
                this.offsetY = -30*(1-Math.cos(phase));
                this.top = map.y+this.baseY+this.offsetY;
                this.view.y = this.baseY+this.offsetY;
            };
        }
	}
}(window));
