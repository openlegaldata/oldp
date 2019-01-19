import $ from 'jquery';

import rangy from 'rangy/lib/rangy-core';
import 'rangy/lib/rangy-serializer.js';


const pluginName = "annotate",
        dataKey = "plugin_" + pluginName;


/***
 *
 *https://www.quirksmode.org/dom/range_intro.html#link8
 *
 * - startOffset: only text content
 * - createRange needs nodes + offset
 *
 * - store startNode + endNode + offets
 * - store node x path
 * - retreive nodes by xpath
 * https://stackoverflow.com/questions/2631820/how-do-i-ensure-saved-click-coordinates-can-be-reloaed-to-the-same-place-even-i/2631931#2631931
 *
 * HOWTO store data for python?
 *
 * @param element
 * @param options
 * @constructor
 */

let Plugin = function (element, options) {
    this.element = element;
    this.$element = $(element);

    this.labels = []; // [{id: Integer, color: String, text: String}]
    this.text = '';
    this.entityPositions = []; // {}

    this.startOffset = 0;
    this.endOffset = 0;
    this.selection_range = null;
    this.selection_text = '';

    this.options = {
    };

    if ($(element).length) { // Check if container element exist
        this.init(options);
        console.log('construct annotator');
    }

    return this;
};

Plugin.prototype = {
    init: function (options) {
        $.extend(this.options, options);

        console.log('init');

        this.text = this.$element.text();

        this.$element.bind('click', { plugin: this, 'foo': 'bar' }, this.setSelectedRange);

        $('#annotator-btn').bind('click', { plugin: this, labelId: 'foo-label' }, this.addLabelByEvent);

        this.addLabel('a', 0, 10, rangy.deserializeRange('0/3/3/5/3/1/5/2:32,0/3/3/5/3/1/5/2:34{61a65735}'));
        this.addLabel('x', 0, 20, rangy.deserializeRange('2/5/3/5/3/1/5/2:19,2/5/3/5/3/1/5/2:45{129ee181}'))
    },
    isValidRange: function(startOffset, endOffset) {
        console.log('valid range: ', this);
      if (startOffset === this.endOffset) {
        return false;
      }
      if (startOffset > this.text.length || endOffset > this.text.length) {
        return false;
      }
      if (startOffset < 0 || endOffset < 0) {
        return false;
      }
      for (let i = 0; i < this.entityPositions.length; i++) {
          // Check if selection overlaps with other entities
        const e = this.entityPositions[i];
        if ((e.start_offset <= startOffset) && (startOffset < e.end_offset)) {
          return false;
        }
        if ((e.start_offset < endOffset) && (endOffset < e.end_offset)) {
          return false;
        }
        if ((startOffset < e.start_offset) && (e.start_offset < endOffset)) {
          return false;
        }
        if ((startOffset < e.end_offset) && (e.end_offset < endOffset)) {
          return false;
        }
      }
      return true;
    },

    resetRange: function() {
      this.startOffset = 0;
      this.endOffset = 0;
    },


    addLabel: function(labelId, startOffset, endOffset, range) {
        if (this.isValidRange(startOffset, endOffset)) {
            const label = {
                start_offset: startOffset,
                end_offset: endOffset,
                label: labelId,
            };
            this.entityPositions.push(label);

            console.log('Add label for ', label);

            // let range = document.createRange();
//
// range.setStart(node, 5);
// range.setEnd(node, 55);

            // let range = this.selection_range;
            let span = document.createElement('span');
            span.textContent = range.toString();
            span.className = 'annotation';

            let button = document.createElement('button');
            button.textContent = 'x';

            span.appendChild(button);

            console.log(range);

            range.deleteContents();
            range.insertNode(span);
        } else {
            console.log('add label: invalid range');
        }
    },

    addLabelByEvent: function(event) {
        console.log('add label from event');

        let plugin = event.data.plugin;

        plugin.addLabel(event.data.labelId, plugin.startOffset, plugin.endOffset, plugin.selection_range);
        plugin.clearSelection();

    },

    removeLabel: function(event, index) {
        console.log('remove label index = ', index);
      // this.$emit('remove-label', index);
    },

    getXPathTo: function(element) {
        console.log('Xpath from: ', element);

        if (element.tagName == 'HTML') {
            return '/HTML[1]';
        }

        if (element===document.body) {
            return '/HTML[1]/BODY[1]';
        }

        let ix= 0;
        let siblings= element.parentNode.childNodes;
        for (let i= 0; i<siblings.length; i++) {
            let sibling= siblings[i];
            if (sibling===element)
                return this.getXPathTo(element.parentNode)+'/'+element.tagName+'['+(ix+1)+']';
            if (sibling.nodeType===1 && sibling.tagName===element.tagName)
                ix++;
        }
    },

    getElementByXPath: function(path) {
      return document.evaluate(path, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    },


    setSelectedRange: function(event) {
        console.log('selected range');
        console.log(this);
        // console.log(foo);
        console.log(event.data);

        let plugin = event.data.plugin;

        // console.log('Xpath result: ', fullPath(document.getElementById('annotator')));

        let start;
        let end;
        let selection_range;

        if (window.getSelection) {
            const range = window.getSelection().getRangeAt(0);
            const preSelectionRange = range.cloneRange();
            preSelectionRange.selectNodeContents(this);
            preSelectionRange.setEnd(range.startContainer, range.startOffset);
            start = preSelectionRange.toString().length;
            end = start + range.toString().length;

            selection_range = range.cloneRange();
            // selection_text =

        } else if (document.selection && document.selection.type !== 'Control') {
            const selectedTextRange = document.selection.createRange();
            const preSelectionTextRange = document.body.createTextRange();
            preSelectionTextRange.moveToElementText(this);
            preSelectionTextRange.setEndPoint('EndToStart', selectedTextRange);
            start = preSelectionTextRange.text.length;
            end = start + selectedTextRange.text.length;

            selection_range = selectedTextRange;
        }

        console.log('Plugin: ', plugin);
        let x = rangy.serializeRange(selection_range);

        console.log('selection_range ', selection_range);
        console.log('ser ', x);
        console.log('der ', rangy.deserializeRange(x));


        // console.log('startContainer ', selection_range.startContainer);
        // console.log(fullPath(selection_range.startContainer));

        // console.log('startOffset ', selection_range.startOffset);

        // console.log('endContainer ', selection_range.endContainer);
        // console.log(fullPath(selection_range.endContainer));



        plugin.selection_range = selection_range;
        plugin.startOffset = start;
        plugin.endOffset = end;
        console.log('setSelectedRange ', start, end);
    },

    makeLabel: function(startOffset, endOffset) {
      const label = {
        id: 0,
        label: -1,
        start_offset: startOffset,
        end_offset: endOffset,
      };
      return label;
    },

    clearSelection: function() {
        if (window.getSelection) {
          if (window.getSelection().empty) {  // Chrome
            window.getSelection().empty();
          } else if (window.getSelection().removeAllRanges) {  // Firefox
            window.getSelection().removeAllRanges();
          }
        } else if (document.selection) {  // IE?
          document.selection.empty();
        }
    },

};

$.fn[pluginName] = function (options) {
    let plugin = this.data(dataKey);

    if (plugin instanceof Plugin) {
        if (typeof options !== 'undefined') {
            plugin.init(options);
        }
    } else {
        plugin = new Plugin(this, options);
        this.data(dataKey, plugin);
    }

    return plugin;
};

