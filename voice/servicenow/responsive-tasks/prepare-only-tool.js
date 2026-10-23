/* Prospective responsive VA tool: produces untrusted candidate fields only.
 * It never creates a task, confirms, calls the guard, or orders a catalog item.
 * Attach only after the responsive agent's unguarded order M2M is removed.
 */
(function(inputs) {
    var names=['employee_name','start_date','delivery_location','manager_name'], proposal={};
    for(var i=0;i<names.length;i++) {
        var value=inputs[names[i]];
        if(typeof value!=='string'||value.length>100||/[\x00-\x1f\x7f]/.test(value)) return {ok:false,error:'bounded_fields_required',order_submitted:false};
        proposal[names[i]]=value.replace(/^\s+|\s+$/g,'');
    }
    return {ok:true,proposal:proposal,authority:'untrusted_candidate',confirmation_required:true,order_submitted:false};
})(inputs);
