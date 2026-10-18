/* Global Background Script. Read-only, no prompts, credentials or session blobs. */
(function () {
    var APP = '200af60f93fb4354e7f2b9fa6aba107d';
    var ITEM = '401b878b93738354e7f2b9fa6aba102f';
    var EXPECTED_USER = '6a0690b893d00b105c8132d47aba1022';
    function print(label, value) {
        gs.print('[SCC Voice Acceptance] ' + label + ': ' + JSON.stringify(value));
    }
    var account = new GlideRecord('sys_cs_consumer_account');
    account.addQuery('provider_application', APP);
    account.orderByDesc('sys_created_on');
    account.setLimit(3);
    account.query();
    while (account.next()) {
        var consumer = account.consumer.getRefRecord();
        print('identity', {
            account: account.getUniqueValue(),
            created: account.getValue('sys_created_on'),
            consumer: account.getValue('consumer'),
            user: consumer.getValue('user_id'),
            inactive: consumer.getValue('inactive'),
            expectedUser: consumer.getValue('user_id') === EXPECTED_USER
        });
        var conversation = new GlideRecord('sys_cs_conversation');
        conversation.addQuery('consumer_account', account.getUniqueValue());
        conversation.orderByDesc('sys_created_on');
        conversation.setLimit(2);
        conversation.query();
        while (conversation.next()) print('conversation', {
            id: conversation.getUniqueValue(),
            state: conversation.getValue('state'),
            consumer: conversation.getValue('consumer'),
            created: conversation.getValue('sys_created_on'),
            updated: conversation.getValue('sys_updated_on')
        });
    }
    var item = new GlideRecord('sc_req_item');
    item.addQuery('cat_item', ITEM);
    item.addQuery('requested_for', EXPECTED_USER);
    item.orderByDesc('sys_created_on');
    item.setLimit(10);
    item.query();
    while (item.next()) print('order', {
        id: item.getUniqueValue(), number: item.getValue('number'),
        request: item.getDisplayValue('request'),
        employee: String(item.variables.employee_name),
        start: String(item.variables.start_date),
        manager: String(item.variables.manager),
        location: String(item.variables.delivery_location)
    });
    var mobile = new GlideRecord('sys_sg_button_instance');
    if (mobile.get('74e2df0393f78354e7f2b9fa6aba1000'))
        print('mobile', { active: mobile.getValue('active') });
    var batch = new GlideRecord('sys_update_set');
    if (batch.get('194a7413933f0754e7f2b9fa6aba1080'))
        print('batch', { state: batch.getValue('state') });
    print('result', { writes: 0 });
})();
