/**
 * Inspired by rangee js
 * - Lukáš Rada
 * - https://github.com/LukasRada/rangee
 * - MIT License
 *
 * Qs:
 * - How to maintain order when adding + removing markers (textNodeIndex)
 *  - serialize all markers when saving
 *
 *
 */

let __assign = function() {
    __assign = Object.assign || function __assign(t) {
        for (let s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (let p in s) if (Object.prototype.hasOwnProperty.call(s, p)) t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
};

let find = function (result, document, relativeSelector) {
    let selector = relativeSelector + '>' + result.selector;
    let element = document.querySelector(selector);
    if (!element) {
        throw new Error('Unable to find element with selector: ' + selector);
    }
    return element.childNodes[result.textNodeIndex];
};
let generateSelector = function (node, relativeTo) {
    let currentNode = node;
    let tagNames = [];
    let textNodeIndex = 0;
    if (node.parentNode) {
        textNodeIndex = childNodeIndexOf(node.parentNode, node);
        while (currentNode) {
            let tagName = currentNode.tagName;
            if (tagName) {
                let nthIndex = computedNthIndex(currentNode);
                let selector = tagName;
                if (nthIndex > 1) {
                    selector += ":nth-of-type(" + nthIndex + ")";
                }
                tagNames.push(selector);
            }
            currentNode = (currentNode.parentNode || currentNode.parentElement);
            if (currentNode == (relativeTo.parentNode || relativeTo.parentElement)) {
                break;
            }
        }
    }
    return { selector: tagNames.reverse().join(">").toLowerCase(), textNodeIndex: textNodeIndex, offset: 0 };
};
let childNodeIndexOf = function (parentNode, childNode) {
    let childNodes = parentNode.childNodes;
    let result = 0;
    for (let i = 0, l = childNodes.length; i < l; i++) {
        if (childNodes[i] === childNode) {
            result = i;
            break;
        }
    }
    return result;
};
let computedNthIndex = function (childElement) {
    let elementsWithSameTag = 0;
    let parent = (childElement.parentNode || childElement.parentElement);
    if (parent) {
        for (let i = 0, l = parent.childNodes.length; i < l; i++) {
            let currentHtmlElement = parent.childNodes[i];
            if (currentHtmlElement === childElement) {
                elementsWithSameTag++;
                break;
            }
            if (currentHtmlElement.tagName === childElement.tagName) {
                elementsWithSameTag++;
            }
        }
    }
    return elementsWithSameTag;
};

let serialize = function (range, relativeTo) {
    console.log('serialize relative to ', relativeTo);

    let start = generateSelector(range.startContainer, relativeTo);
    start.offset = range.startOffset;
    let end = generateSelector(range.endContainer, relativeTo);
    end.offset = range.endOffset;
    return { start: start, end: end };
};
let deserialize = function (result, document, relativeTo) {
    console.log('deserialize doc ', document);

    let relativeSelector = generateSelector(relativeTo, document);

    let range = document.createRange();
    let startNode = find(result.start, document, relativeSelector.selector);
    let endNode = find(result.end, document, relativeSelector.selector);
    if (startNode.nodeType != Node.TEXT_NODE && startNode.firstChild) {
        startNode = startNode.firstChild;
    }
    if (endNode.nodeType != Node.TEXT_NODE && endNode.firstChild) {
        endNode = endNode.firstChild;
    }
    if (startNode) {
        range.setStart(startNode, result.start.offset);
    }
    if (endNode) {
        range.setEnd(endNode, result.end.offset);
    }
    return range;
};

let Annotator = (function () {
    function Annotator(options) {
        let _this = this;
        this.serializeAtomic = function (range) {
            let atomicRanges = _this.createAtomicRanges(range);
            let relativeTo = _this.options.body;

            let serialized = atomicRanges
                .map(function (range) { return serialize(range.cloneRange(), relativeTo); })
                .map(function (serializedRange) { return JSON.stringify(serializedRange); })
                .join("|");

            return serialized;
        };
        this.deserilaizeAtomic = function (representation) {
            let document = _this.options.document;
            let relativeTo = _this.options.container;

            let serializedRanges = representation
                .split("|")
                .map(function (decompressedRangeRepresentation) { return JSON.parse(decompressedRangeRepresentation); })
                .reverse()
                .map(function (serializedRange) { return deserialize(serializedRange, document, relativeTo); });
            return serializedRanges;
        };
        this.serialize = function (range) {
            let relativeTo = _this.options.body;

            let serialized = serialize(range.cloneRange(), relativeTo);

            return JSON.stringify(serialized);
        };
        this.deserialize = function (serialized) {
            let decompressedParsed = JSON.parse(serialized);
            let document = _this.options.document;
            let relativeTo = _this.options.container;

            return deserialize(decompressedParsed, document, relativeTo);
        };
        this.createAtomicRanges = function (range) {
            // text
            if (range.startContainer === range.endContainer && range.startContainer.nodeType === Node.TEXT_NODE) {
                return [range];
            }
            let documentAsAny = _this.options.document; // IE does not know the right spec signature for createTreeWalker
            // elements
            let treeWalker = documentAsAny.createTreeWalker(range.commonAncestorContainer, NodeFilter.SHOW_ALL, function (node) { return NodeFilter.FILTER_ACCEPT; }, false);
            let startFound = false;
            let endFound = false;
            let atomicRanges = [];
            let node;
            while (node = treeWalker.nextNode()) {
                if (node === range.startContainer) {
                    startFound = true;
                }
                if (node.nodeType === Node.TEXT_NODE && startFound && !endFound && node.textContent && node.textContent.trim().length > 0) {
                    let atomicRange = _this.options.document.createRange();
                    atomicRange.setStart(node, node === range.startContainer ? range.startOffset : 0);
                    atomicRange.setEnd(node, node === range.endContainer ? range.endOffset : node.length);
                    atomicRanges.push(atomicRange);
                }
                if (node === range.endContainer) {
                    endFound = true;
                }
            }
            return atomicRanges;
        };
        this.loadRange = function(serializedRange) {

            const ranges = _this.deserilaizeAtomic(serializedRange);

            ranges.reverse().forEach(function(range) {
                let btn = document.createElement('button');
                btn.innerText = 'x';
                btn.addEventListener('click', function(event) {
                    console.log('remove this', this, this.textContent);
                    // jquery.replaceWith innerHtml
                    let span = this.parentElement;
                    let p = span.parentElement;


                    this.remove();
                    p.replaceChild(document.createTextNode(span.textContent), span);
                    // TODO text node destroys selectors

                    // this.parentElement.className = '';

                });

                const highlight = document.createElement('span');
                highlight.className = 'annotation';
                highlight.textContent = range.toString();
                // highlight.appendChild(btn);

                // console.log('toString ', range.toString());

                // range.surroundContents(highlight);

                range.deleteContents();
                range.insertNode(highlight);


            });
        };
        this.saveRange = function() {
            const selection = document.getSelection();
            if (selection && selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);


                if (range && range.toString().length > 0) {


                    let container = _this.options.container;
                    console.log(range.startContainer);

                    if (container.contains(range.startContainer) && container.contains(range.endContainer)) {
                        console.log('inside');


                        const rangeRepresentation = _this.serializeAtomic(range);
                        console.log(rangeRepresentation);
                        // rangeRepresentationStorage.push(rangeRepresentation);
                        selection.removeAllRanges();

                        this.loadRange(rangeRepresentation);
                    } else {
                        console.log('outside');
                    }

                }
            }
        };
        this.options = __assign({}, options);
    }
    return Annotator;
}());

module.exports = Annotator;
