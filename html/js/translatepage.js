$(document).ready(function() {

/* Pootle namespace */
  $.pootle = {};

/*
 * FOCUS
 */

  // Set initial focus on page load
  var initialFocus = $(".translate-original-focus textarea").focus();
  $.pootle.focusedElement = initialFocus.get(0);

  // Update focus when appropriate
  $(".focusthis").focus(function(e) {
    $.pootle.focusedElement = e.target;
  });


/*
 * REPLACEMENTS
 */

  // Write TM results into the currently focused element
  $(".writetm").click(function() {
    var tmtext = $(".tm-translation", this).text();
    var element = $($.pootle.focusedElement);
    var start = element.caret().start + tmtext.length;
    element.val(element.caret().replace(tmtext));
    element.caret(start, start);
  });

  // Write special chars into the currently focused element
  $(".writespecial").click(function() {
    var specialtext = $(this).text();
    var element = $($.pootle.focusedElement);
    var start = element.caret().start + specialtext.length;
    element.val(element.caret().replace(specialtext));
    element.caret(start, start);
  });


/*
 * COPY ORIGINAL TRANSLATION
 */

  $(".copyoriginal").click(function() {
      var source =  $("#id_source_f_0").val().replace("\n", "\\n\n", "g").replace("\t", "\\t", "g");
      var splural_element = $("#id_source_f_1");
      if (splural_element.length != 0) {
        var source_plural = splural_element.val().replace("\n", "\\n\n", "g").replace("\t", "\\t", "g");
      } else {
        var source_plural = source;
      }

      var targets = $("[id^=id_target_f_]");
      $.each(targets, function(i) {
          newval = i == 0 ? source : source_plural;
          $(this).val(newval);
          $(this).focus();
      });
  });


/*
 * UNFUZZY
 */

/*
 *  For future enhancements like multiple edit boxes, please note
 *  that the selector is based on a class, so it must be modified
 *  to get the textarea's element ID and select the checkbox to
 *  remove the "checked" attribute according to that value.
 */
  var keepstate = false;
  $("textarea.translation").bind("keyup blur", function() {
    if (!keepstate && $(this).attr("defaultValue") != $(this).val()) {
      var checkbox = $("input.fuzzycheck[checked]");
      checkbox.removeAttr("checked");
      checkbox.parent().animate({ backgroundColor: "#dafda5 !important" }, "slow")
                       .animate({ backgroundColor: "#ffffff !important" }, "slow");
      $(this).parent().parent().removeClass("translate-translation-fuzzy");
      keepstate = true;
    }
  });

  $("input.fuzzycheck").click(function() {
    keepstate = true;
    $(this).parent().parent().parent().toggleClass("translate-translation-fuzzy");
  });

/*
 * SUGGESTIONS
 */

/* INLINE SUGGESTIONS */

  $(".collapse").click(function(event) {
    event.preventDefault();
    $(this).parent().siblings().slideToggle('fast');
  });
  $(".collapse").parent().siblings().hide();

/* REVIEWING SUGGESTIONS */

  function handlesuggestions(url, data) {
    $.post(url,
           {data: JSON.stringify(data)},
           function(rdata) {
             $("#response").remove();
             if (rdata.status == "success") {
               // Remove processed suggestion
               $.each(rdata.del_ids, function() {
                 var deleted = this[0] + "-" + this[1];
                 $("#suggestion" + deleted).fadeOut(500);
               });
               // If it's an accept, then update the textareas
               if (rdata.hasOwnProperty("accepted_id")) {
                 var textareas = $("#translate-suggestion-container").siblings("textarea");
                 var accepted= rdata.accepted_id[0] + "-" + rdata.accepted_id[1];
                 var inputs = $("#suggestion" + accepted + " .translate-suggestion").children().siblings("input");
                 $.each(textareas, function(i) {
                   $(this).val(inputs.eq(i).val());
                 });
               }
               // If there are no more suggestions left, remove
               // the current translation block.
               if (!rdata.diffs.hasOwnProperty("0")) {
                 $("#translate-original-container").fadeOut(500);
               }
               // Update current diff otherwise
               else {
                 var current = $("#translate-original-container .translate-original-block");
                 var forms = rdata.diffs;
                 $.each(current, function() {
                   var insertat = $("div", this);
                   $.each(forms, function() {
                     $(insertat).html(this.diff);
                   });
                 });
               }
             }
             $("div#translate-suggestion-container:first").prepend(
              '<h2 id="response">' + rdata.message + '</h2>'
              );
           }, "json");
  }

    $("#translate-suggestion-container .rejectsugg").click(function() {
      var element = $(this).parent().parent();
      var uid = $('.translate-original input#id_id').val();
      var suggid = $(this).siblings("input.suggid").val();
      var url = l('/suggestion/reject/') + uid + '/' + suggid;
      $.post(url, {'reject': 1},
             function(rdata) {
               $("#response").remove();
               element.fadeOut(500);
             }, "json");
      return false;
    });

    $("#translate-suggestion-container .acceptsugg").click(function() {
      var element = $(this).parent().parent();
      var uid = $('.translate-original input#id_id').val();
      var suggid = $(this).siblings("input.suggid").val();
      var url = l('/suggestion/accept/') + uid + '/' + suggid;
      $.post(url, {'accept': 1},
             function(rdata) {
               $("#response").remove();
               $.each(rdata.newtargets, function(i, target) {
                 $("textarea#id_target_f_" + i).val(target).focus();
               });
               $.each(rdata.newdiffs, function(suggid, sugg) {
                 $.each(sugg, function(i, target) {
                   $("#suggdiff-" + suggid + "-" + i).html(target);
                 });
               });
               element.fadeOut(500);
             }, "json");
      return false;
    });

});
