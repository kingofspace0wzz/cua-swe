(function (window) {

    //extend & promote createjs.Container functions to window
    createjs.extend(Interface, createjs.Container);
    window.Interface = createjs.promote(Interface, "Container");

	//constructor
	function Interface() {

        this.init = function(){
            this.Container_constructor();
            this.screenWidth = window.Game.getWidth();
            this.screenHeight = window.Game.getHeight();
            this.box16 = window.Game.box16;
            this.fontSize = this.box16 * 0.75;
            this.fontColor = "#ffffff";
            this.tipValue = "";
            this.tipWidth = 0;
            this.tipContainer = new createjs.Container();
            this.tipBg = new createjs.Shape();
            this.tipText = new createjs.Text("", (this.fontSize * 0.6) + "px prstart", "#ffffff");
            this.tipText.lineHeight = this.fontSize * 0.9;
            this.tipContainer.addChild(this.tipBg, this.tipText);
            //this.build();
        };

        this.build = function(){
            this.removeAllChildren();
            //positioning buttons
            var bigBox = this.box16*4;
            var topY = bigBox / 2;
            var leftX = topY;
            //set colors to theme
            this.main_color2 = window.Game.theme.main_color2;
            this.main_color3 = window.Game.theme.main_color3;
            //main game ui
            this.menu_button = new Button("_a", leftX, topY, bigBox/2, bigBox/2, this.main_color2, "#000000", "#ffffff", "#ffffff");
            this.menu_button.setFontSize(0.5);
            this.time_button = new Button(window.timer.toString(),(leftX*2.75), topY, Math.floor(bigBox*1.25), bigBox/2,"#000000",this.main_color2,"#ffffff","#ffffff");
            this.time_button.setFontSize(0.75);
            this.addChild(this.menu_button, this.time_button); //draw level container
            this.addChild(this.tipContainer);
            this.updateTipBox(true);
        };

        this.removeInterface = function(){ this.removeAllChildren(); };

        //update
        this.tick = function (delta) {
            this.updateTimeButton();
            this.updateTipBox();
            if (this.menu_button.isClicked() || this.time_button.isClicked()){ //open dialog
                window.Game.pauseGame();
            }
        };

        this.updateTimeButton = function(useGlobalScore){ 
            useGlobalScore = (useGlobalScore === undefined) ? false : true;
            this.time_button.setText(useGlobalScore == true ? window.Game.score : window.timer.toString()); 
        };

        this.updateTipBox = function(force){
            force = force === true;
            var tip = "";
            if (window.storageManager && typeof window.storageManager.tipString === "string") {
                tip = window.storageManager.tipString.trim();
            }
            var maxWidth = Math.min(this.screenWidth - (this.box16 * 2), this.box16 * 12);
            if (!force && tip === this.tipValue && maxWidth === this.tipWidth) return;

            this.tipValue = tip;
            this.tipWidth = maxWidth;

            if (!tip){
                this.tipContainer.visible = false;
                return;
            }

            this.tipContainer.visible = true;
            this.tipText.text = tip;
            this.tipText.lineWidth = maxWidth;
            var padding = this.box16 * 0.35;
            var x = Math.max(this.box16 * 0.5, (this.screenWidth - maxWidth) / 2);
            var y = this.screenHeight - (this.box16 * 1.5);
            var height = this.tipText.getMeasuredHeight();
            y = Math.max(this.box16 * 0.5, y - height);
            this.tipText.x = x;
            this.tipText.y = y;
            this.tipBg.graphics.clear()
                .beginFill("rgba(0,0,0,0.7)")
                .drawRoundRect(
                    x - padding,
                    y - padding,
                    maxWidth + padding * 2,
                    height + padding * 2,
                    this.box16 * 0.4
                );
        };

        //initiate prototype variables
        this.init();
	}
}(window));
