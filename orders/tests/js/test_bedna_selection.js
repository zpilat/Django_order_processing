/* Run with Node, or load after scan_parser.js and bedna_selection.js in a browser. */
(function (root) {
    'use strict';

    const selection = typeof require === 'function'
        ? require('../../static/orders/js/bedna_selection.js') : root.OrderBednaSelection;
    const parser = typeof require === 'function'
        ? require('../../static/orders/js/scan_parser.js') : root.OrderScanParser;
    const options = [
        { value: '', textContent: '---------' },
        { value: 'wrong', textContent: '701329 (EUR-1031780751800-10x20)' },
        { value: 'longer', textContent: '1031780 (EUR-OTHER-10x20)' },
        { value: 'exact', textContent: '103178 (EUR-OTHER-10x20)' },
    ];
    let passed = 0;

    function expectMatches(query, expected, exactOnly = false) {
        const actual = selection.matchingOptions(options, query, exactOnly).map(option => option.value);
        if (JSON.stringify(actual) !== JSON.stringify(expected)) {
            throw new Error('Query ' + query + ': expected ' + JSON.stringify(expected) + ', got ' + JSON.stringify(actual));
        }
        passed += 1;
    }

    expectMatches('103178', ['exact']);
    expectMatches(' 103178 ', ['exact']);
    expectMatches('3178', ['longer', 'exact']);
    expectMatches('701329', ['wrong']);
    expectMatches('1031780751800', []);
    expectMatches('EUR', []);
    expectMatches('10x20', []);
    expectMatches('EUR 103178', []);
    expectMatches('', []);
    expectMatches('   ', []);
    expectMatches('3178', [], true);
    expectMatches('1031780751800', [], true);

    for (const code of ['103178', 'BEDNA:103178', '/bedny/scan/103178/', 'https://example.test/bedny/scan/103178/', 'HTTPS://EXAMPLE.TEST/BEDNY/SCAN/103178/']) {
        const parsed = parser.parse(code);
        if (parsed.type !== 'bedna') {
            throw new Error('Expected crate code: ' + code);
        }
        expectMatches(parsed.value, ['exact'], true);
    }

    if (typeof document !== 'undefined' && document.querySelector('.patro-form')) {
        const input = document.querySelector('.bedna-search-input');
        const select = document.querySelector('.js-bedna');
        input.focus();
        input.value = '103178';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        const results = document.querySelectorAll('.bedna-search-option');
        if (results.length !== 1 || results[0].dataset.optionValue !== 'exact') {
            throw new Error('Reader input must offer only the exact crate');
        }
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
        if (select.value !== 'exact') {
            throw new Error('Reader Enter must select crate 103178');
        }
        passed += 1;

        input.dispatchEvent(new Event('focus'));
        if (document.querySelectorAll('.bedna-search-option').length !== 1) {
            throw new Error('Focusing a selected crate must still show its exact match');
        }
        passed += 1;

        input.value = '1031780751800';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        if (document.querySelector('.bedna-search-option') || select.value) {
            throw new Error('An order number must not select a crate');
        }
        passed += 1;

        document.querySelector('.scan-bedna-button').click();
        const scannerInput = document.getElementById('bedna-scanner-manual-input');
        const scannerForm = document.getElementById('bedna-scanner-manual-form');
        for (const code of ['103178', 'BEDNA:103178', '/bedny/scan/103178/', 'https://example.test/bedny/scan/103178/']) {
            select.value = '';
            scannerInput.value = code;
            scannerForm.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
            if (select.value !== 'exact') {
                throw new Error('Scanner must select crate 103178: ' + code);
            }
            passed += 1;
        }
    }

    root.bednaSelectionTestResult = 'PASS: ' + passed + ' crate selection cases';
    if (typeof console !== 'undefined') {
        console.log(root.bednaSelectionTestResult);
    }
})(typeof window !== 'undefined' ? window : globalThis);
