import $ from 'jquery';

const pluginName = "annotate",
        dataKey = "plugin_" + pluginName;

let Plugin = function (element, options) {
    this.element = element;
    this.$element = $(element);

    this.labels = Array; // [{id: Integer, color: String, text: String}]
    this.text = String;
    this.entityPositions = Array;

    this.startOffset = 0;
    this.endOffset = 0;

    this.options = {
    };

    if ($(element).length) { // Check if container element exist
        this.init(options);
        console.log('construct annotator');
    }
};

Plugin.prototype = {
    init: function (options) {
        $.extend(this.options, options);

        console.log('init');

        this.$element.bind('click', { foo: 'xxx', plugin: this }, this.setSelectedRange);

        // this.element.click(this.setSelectedRange);
    },

    setSelectedRange: function(e) {
        console.log('selected range');
        console.log(this);
        // console.log(foo);
        console.log(e.data);

        let plugin = e.data.plugin;

        let start;
        let end;
        if (window.getSelection) {
            const range = window.getSelection().getRangeAt(0);
            const preSelectionRange = range.cloneRange();
            preSelectionRange.selectNodeContents(this);
            preSelectionRange.setEnd(range.startContainer, range.startOffset);
            start = preSelectionRange.toString().length;
            end = start + range.toString().length;
        } else if (document.selection && document.selection.type !== 'Control') {
            const selectedTextRange = document.selection.createRange();
            const preSelectionTextRange = document.body.createTextRange();
            preSelectionTextRange.moveToElementText(this);
            preSelectionTextRange.setEndPoint('EndToStart', selectedTextRange);
            start = preSelectionTextRange.text.length;
            end = start + selectedTextRange.text.length;
        }

        plugin.startOffset = start;
        plugin.endOffset = end;
        console.log('setSelectedRange ', start, end);
    },

    validRange: function() {
      if (this.startOffset === this.endOffset) {
        return false;
      }
      if (this.startOffset > this.text.length || this.endOffset > this.text.length) {
        return false;
      }
      if (this.startOffset < 0 || this.endOffset < 0) {
        return false;
      }
      for (let i = 0; i < this.entityPositions.length; i++) {
        const e = this.entityPositions[i];
        if ((e.start_offset <= this.startOffset) && (this.startOffset < e.end_offset)) {
          return false;
        }
        if ((e.start_offset < this.endOffset) && (this.endOffset < e.end_offset)) {
          return false;
        }
        if ((this.startOffset < e.start_offset) && (e.start_offset < this.endOffset)) {
          return false;
        }
        if ((this.startOffset < e.end_offset) && (e.end_offset < this.endOffset)) {
          return false;
        }
      }
      return true;
    },

    resetRange: function() {
      this.startOffset = 0;
      this.endOffset = 0;
    },

    addLabel: function(labelId) {
        let plugin = event.data.plugin;

      if (this.validRange()) {
        const label = {
          start_offset: this.startOffset,
          end_offset: this.endOffset,
          label: labelId,
        };
        console.log('Add label for ', labelId);
        // this.$emit('add-label', label);
      } else {
          console.log('invalid range');
      }
    },

    removeLabel: function(index) {
        console.log('remove label index = ', index);
      // this.$emit('remove-label', index);
    },

    makeLabel: function(startOffset, endOffset) {
      const label = {
        id: 0,
        label: -1,
        start_offset: startOffset,
        end_offset: endOffset,
      };
      return label;
    }
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

