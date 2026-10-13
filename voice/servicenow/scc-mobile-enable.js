/* Global Background Script: activate only the prepared SCC demo entry.
 * ROLLBACK=true hides the same entry again. Capture metadata afterwards.
 */
(function () {
    var ROLLBACK = false;
    var button = new GlideRecord('sys_sg_button');
    var entry = new GlideRecord('sys_sg_button_instance');
    var mapping = new GlideRecord('sys_sg_alp_quick_action_map');
    if (!button.get('b0e217cf93b78354e7f2b9fa6aba1028') ||
        !entry.get('74e2df0393f78354e7f2b9fa6aba1000') ||
        !mapping.get('78e2df0393f78354e7f2b9fa6aba1003'))
        throw new Error('Prepared SCC mobile entry is missing');
    if (button.getValue('name') !== 'SCC Laptop Voice' ||
        button.getValue('link_url') !== 'https://strix-alloy.tail7f425a.ts.net/scc-demo/' ||
        button.getValue('external_browser') !== '1' ||
        entry.getValue('button') !== button.getUniqueValue() ||
        entry.getValue('parent') !== 'ad7cc08177a72300454792718a1061ab' ||
        mapping.getValue('quick_action_button') !== entry.getUniqueValue() ||
        mapping.getValue('applet_launcher') !== entry.getValue('parent'))
        throw new Error('SCC mobile relationships changed; no write');
    var desired = ROLLBACK ? '0' : '1';
    var writes = 0;
    if (entry.getValue('active') !== desired) {
        entry.setWorkflow(false);
        entry.setValue('active', desired);
        if (!entry.update()) throw new Error('Could not save mobile entry');
        writes++;
    }
    entry.get('74e2df0393f78354e7f2b9fa6aba1000');
    if (entry.getValue('active') !== desired)
        throw new Error('Mobile activation readback failed');
    gs.print('[SCC Mobile Enable] ' + JSON.stringify({
        ok: true, active: desired === '1', writes: writes,
        button: button.getUniqueValue(), entry: entry.getUniqueValue(),
        url: button.getValue('link_url')
    }));
})();
