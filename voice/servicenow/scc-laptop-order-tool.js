(function(inputs) {
    // Dedicated, zero-price demo item. Standard CartJS creates REQ/RITM.
    var itemId = '401b878b93738354e7f2b9fa6aba102f';
    function clean(name) { return String(inputs[name] || '').replace(/^\s+|\s+$/g, ''); }
    function fail(message) { return {ok:false,error:message,retry_automatically:false}; }
    if (clean('confirmed').toLowerCase() != 'true')
        return fail('Bitte zuerst die vollständige Zusammenfassung ausdrücklich bestätigen lassen.');
    var employee = clean('employee_name'), date = clean('start_date');
    var location = clean('delivery_location'), managerName = clean('manager_name');
    if (!employee || employee.length > 100 || !location || location.length > 100)
        return fail('Mitarbeitername und Standort sind erforderlich.');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return fail('Eintrittsdatum als YYYY-MM-DD benötigt.');
    var gd = new GlideDate();
    gd.setValue(date);
    if (gd.getValue() != date) return fail('Ungültiges Eintrittsdatum.');

    var user = new GlideRecordSecure('sys_user');
    if (!user.get(gs.getUserID()) || user.getValue('user_name') == 'guest')
        return fail('Angemeldeter Anforderer erforderlich.');
    var requesterId = user.getUniqueValue(), managerId = '';
    if (!managerName) managerName = String(user.getDisplayValue());
    if (managerName.toLowerCase() == String(user.getDisplayValue()).toLowerCase()) {
        managerId = requesterId;
    } else {
        var manager = new GlideRecordSecure('sys_user');
        manager.addQuery('active', true);
        manager.addQuery('name', managerName);
        manager.setLimit(2);
        manager.query();
        if (!manager.next()) return fail('Vorgesetzter nicht eindeutig gefunden. Bitte den vollständigen Namen nennen.');
        managerId = manager.getUniqueValue();
        if (manager.next()) return fail('Mehrere Vorgesetzte mit diesem Namen gefunden.');
    }
    var item = new GlideRecordSecure('sc_cat_item');
    if (!item.get(itemId) || item.getValue('active') != '1') return fail('Demo-Katalogelement nicht verfügbar.');

    // Reconcile repeated demo turns. This is not an atomic, distributed idempotency lock.
    var previous = new GlideRecordSecure('sc_req_item');
    previous.addQuery('cat_item', itemId);
    previous.addQuery('request.requested_for', requesterId);
    previous.addQuery('sys_created_on', '>=', gs.hoursAgoStart(24));
    previous.orderByDesc('sys_created_on');
    previous.setLimit(50);
    previous.query();
    while (previous.next()) {
        if (String(previous.variables.employee_name) == employee &&
            String(previous.variables.start_date) == date &&
            String(previous.variables.manager) == managerId &&
            String(previous.variables.delivery_location) == location) {
            return {ok:true,reused:true,request_number:previous.request.getDisplayValue(),
                request_id:previous.getValue('request'),requested_item_id:previous.getUniqueValue(),
                requested_item_number:previous.getValue('number'),employee_name:String(previous.variables.employee_name),
                start_date:String(previous.variables.start_date),delivery_location:String(previous.variables.delivery_location),
                manager_id:String(previous.variables.manager),manager_name:String(previous.variables.manager.getDisplayValue()),demo_only:true};
        }
    }
    try {
        var cart = new sn_sc.CartJS('SCC_Laptop_' + gs.generateGUID());
        var added = cart.addToCart({sysparm_id:itemId,sysparm_quantity:'1',
            variables:{employee_name:employee,
            start_date:date,manager:managerId,delivery_location:location}});
        var lines = cart.getCartItems();
        if (!lines.next() || lines.getValue('cat_item') != itemId || lines.getValue('quantity') != '1')
            return fail('Warenkorb enthält nicht die erwartete Laptop-Position. Es wurde nichts abgesendet.');
        if (lines.next()) return fail('Warenkorb enthält unerwartete weitere Positionen. Es wurde nichts abgesendet.');
        var result = cart.submitOrder({requested_for:requesterId});
        if (!result || !result.request_id)
            return fail('Kein eindeutiges Bestellergebnis. Vor einem erneuten Versuch die Anforderungen prüfen.');
        var ritm = new GlideRecordSecure('sc_req_item');
        ritm.addQuery('request', result.request_id);
        ritm.addQuery('cat_item', itemId);
        ritm.setLimit(1);
        ritm.query();
        if (!ritm.next()) return {ok:false,request_number:String(result.request_number || ''),
            request_id:String(result.request_id),error:'Anforderung vorhanden, Bestellposition fehlt. Vor erneutem Bestellen prüfen.',retry_automatically:false,demo_only:true};
        return {ok:true,reused:false,request_number:ritm.request.getDisplayValue(),
            request_id:ritm.getValue('request'),requested_item_id:ritm.getUniqueValue(),
            requested_item_number:ritm.getValue('number'),employee_name:String(ritm.variables.employee_name),
            start_date:String(ritm.variables.start_date),delivery_location:String(ritm.variables.delivery_location),
            manager_id:String(ritm.variables.manager),manager_name:String(ritm.variables.manager.getDisplayValue()),demo_only:true};
    } catch (error) {
        gs.error('[SCC Laptop] Bestellergebnis unklar: ' + String(error.message || error));
        return fail('Bestellergebnis unklar. Anforderungen prüfen; nicht automatisch erneut bestellen.');
    }
})(inputs);
