(function (window) {
    function ensurePath(root, path) {
        var parts = path.split(".");
        var current = root;
        for (var i = 0; i < parts.length; i++) {
            current[parts[i]] = current[parts[i]] || {};
            current = current[parts[i]];
        }
        return current;
    }

    function makeUnsupported(method) {
        return function (request) {
            if (request && typeof request.failure === "function") {
                request.failure({
                    request: request,
                    response: {
                        errorType: "UNSUPPORTED",
                        method: method
                    }
                });
            }
        };
    }

    var inapp = ensurePath(window, "google.payments.inapp");
    inapp.buy = makeUnsupported("buy");
    inapp.consumePurchase = makeUnsupported("consumePurchase");
    inapp.getPurchases = makeUnsupported("getPurchases");
    inapp.getSkuDetails = makeUnsupported("getSkuDetails");
}(window));
