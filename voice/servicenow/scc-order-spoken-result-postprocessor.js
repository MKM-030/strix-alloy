/* Native AIAgentConstants.POST_SCRIPT_TEMPLATE contract:
 * output = raw tool output; context = additional context.
 * Return { processed_output: primitive or JSON }.
 * No database reads, writes, model calls, or order execution.
 */
(function (output, context) {
    var uncertain = 'Das Bestellergebnis ist unklar; bitte pr\u00fcfen Sie die Anforderungen und bestellen Sie nicht erneut.';
    function result(text) { return { processed_output: text }; }
    function parse(value) {
        return typeof value === 'string' ? JSON.parse(value) : value;
    }
    function text(value, max) {
        if (typeof value !== 'string') return '';
        var clean = value.replace(/^\s+|\s+$/g, '');
        return clean && clean.length <= max && !/[<>\r\n]/.test(clean) ? clean : '';
    }
    try {
        var data = parse(output);
        if (data && typeof data === 'object' && Object.prototype.hasOwnProperty.call(data, 'tool_response'))
            data = parse(data.tool_response);
        if (!data || typeof data !== 'object' || data.ok !== true ||
                data.demo_only !== true || typeof data.reused !== 'boolean' ||
                data.catalog_item_id !== '401b878b93738354e7f2b9fa6aba102f')
            return result(uncertain);
        var employee = text(data.employee_name, 100);
        var catalog = text(data.catalog_item_name, 200);
        if (!employee || !catalog || !/^REQ[0-9]{7}$/.test(data.request_number) ||
                !/^RITM[0-9]{7}$/.test(data.requested_item_number) ||
                !/^[0-9a-f]{32}$/.test(data.request_id) ||
                !/^[0-9a-f]{32}$/.test(data.requested_item_id))
            return result(uncertain);
        var state = data.reused ? 'ist bereits vorhanden' : 'wurde angelegt';
        return result('Die Demo-Anforderung f\u00fcr ' + employee + ' mit Artikel ' + catalog + ' ' + state +
            ': ' + data.request_number + ', Position ' + data.requested_item_number + '.');
    } catch (error) {
        return result(uncertain);
    }
})(output, context);
