(function (root) {
    "use strict";

    function cleanCode(rawValue) {
        return String(rawValue || "").trim().toUpperCase();
    }

    function parseUrl(value) {
        try {
            return new URL(value, root.location ? root.location.origin : "http://localhost");
        } catch (error) {
            return null;
        }
    }

    function parseScanValue(rawValue) {
        const value = cleanCode(rawValue);
        if (!value) {
            return { type: "empty", raw: rawValue, code: value };
        }

        const bednaPrefix = value.match(/^BEDNA:(\d+)$/);
        if (bednaPrefix) {
            return { type: "bedna", raw: rawValue, code: value, value: bednaPrefix[1], source: "prefix" };
        }

        const sarzePrefix = value.match(/^SARZE:S?(\d+)$/);
        if (sarzePrefix) {
            return { type: "sarze", raw: rawValue, code: value, value: sarzePrefix[1], source: "prefix" };
        }

        const sarzeCode = value.match(/^S(\d+)$/);
        if (sarzeCode) {
            return { type: "sarze", raw: rawValue, code: value, value: sarzeCode[1], source: "code" };
        }

        const pracovisteCode = value.match(/^P([1-6])$/);
        if (pracovisteCode) {
            return { type: "pracoviste", raw: rawValue, code: value, value: pracovisteCode[1], source: "code" };
        }

        if (/^\d+$/.test(value)) {
            return { type: "bedna", raw: rawValue, code: value, value: value, source: "number" };
        }

        const url = parseUrl(value);
        if (url) {
            const bednaMatch = url.pathname.match(/^\/bedny\/scan\/(\d+)\/?$/);
            if (bednaMatch) {
                return { type: "bedna", raw: rawValue, code: value, value: bednaMatch[1], source: "url" };
            }
        }

        return { type: "unknown", raw: rawValue, code: value };
    }

    root.OrderScanParser = {
        parse: parseScanValue,
    };

    if (typeof module !== "undefined" && module.exports) {
        module.exports = root.OrderScanParser;
    }
})(typeof window !== "undefined" ? window : globalThis);
