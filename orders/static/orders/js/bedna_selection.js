(function (root) {
    "use strict";

    function numberFromOption(option) {
        const match = option.textContent.trim().match(/^(\d+)(?:\s|\(|$)/);
        return match ? match[1] : '';
    }

    function matchingOptions(options, query, exactOnly = false) {
        const number = String(query || '').trim();
        if (!/^\d+$/.test(number)) {
            return [];
        }
        const usableOptions = Array.from(options).filter(option => option.value);
        const exactMatch = usableOptions.find(option => numberFromOption(option) === number);
        if (exactMatch) {
            return [exactMatch];
        }
        if (exactOnly) {
            return [];
        }
        return usableOptions.filter(option => numberFromOption(option).includes(number));
    }

    root.OrderBednaSelection = { numberFromOption, matchingOptions };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = root.OrderBednaSelection;
    }
})(typeof window !== 'undefined' ? window : globalThis);
