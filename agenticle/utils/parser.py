import xml.parsers.expat
from collections import defaultdict


class XmlNode:
    def __init__(self, tag, attributes=None):
        self.tag = tag
        self.attributes = attributes or {}
        self.text = ""
        self.children = []
        self._children_map = {}
    
    def get_children(self):
        return list(self._children_map.values())[0]

    def _add_child(self, child_node):
        self.children.append(child_node)
        if child_node.tag not in self._children_map:
            self._children_map[child_node.tag] = []
        self._children_map[child_node.tag].append(child_node)

    def __getattr__(self, name):
        if name in self._children_map:
            nodes = self._children_map[name]
            return nodes[0] if len(nodes) == 1 else nodes
        return None

    def __repr__(self):
        child_tags = [child.tag for child in self.children]
        # 在预览中也显示根节点的文本
        text_preview = self.text.strip().replace('\n', ' ')
        if len(text_preview) > 20:
            text_preview = text_preview[:17] + "..."
        return (f"<XmlNode tag='{self.tag}' text='{text_preview}' children={child_tags}>")


class IncrementalXmlParser:
    # --- 新功能: 定义一个常量来代表根节点 ---
    ROOT = "__ROOT__"

    def __init__(self, root_tag="response"):
        self._root_tag = root_tag
        self._parser = xml.parsers.expat.ParserCreate("UTF-8")
        self._parser.StartElementHandler = self._handle_start_element
        self._parser.EndElementHandler = self._handle_end_element
        self._parser.CharacterDataHandler = self._handle_char_data
        
        self.on_enter_tag = None
        self.on_exit_tag = None
        self._streaming_callbacks = defaultdict(list)

        self.root = XmlNode(self._root_tag)
        self._node_stack = [self.root]
        
        self._parser.Parse(f"<{self._root_tag}>".encode('utf-8'), 0)

    @property
    def result(self):
        return self.root

    def register_streaming_callback(self, tag_name, callback):
        """
        为指定的标签注册一个流式回调。
        使用 IncrementalXmlParser.ROOT 来为根节点的裸文本注册回调。
        """
        if callable(callback):
            self._streaming_callbacks[tag_name].append(callback)

    def _handle_start_element(self, name, attrs):
        if name == self._root_tag:
            return

        if self.on_enter_tag:
            self.on_enter_tag(name, attrs)

        new_node = XmlNode(name, attrs)
        self._node_stack[-1]._add_child(new_node)
        self._node_stack.append(new_node)

    def _handle_end_element(self, name):
        if name == self._root_tag:
            return
            
        if self._node_stack and self._node_stack[-1].tag == name:
            self._node_stack.pop()
            if self.on_exit_tag:
                self.on_exit_tag(name)

    def _handle_char_data(self, data):
        if not self._node_stack:
            return

        current_node = self._node_stack[-1]
        
        target_tag = self.ROOT if len(self._node_stack) == 1 else current_node.tag
        
        if target_tag in self._streaming_callbacks:
            for callback in self._streaming_callbacks[target_tag]:
                try:
                    callback(data)
                except Exception as e:
                    print(f"Error in streaming callback for tag '{target_tag}': {e}")
        else:
            current_node.text += data

    def feed(self, chunk):
        try:
            self._parser.Parse(chunk, False)
        except xml.parsers.expat.error as e:
            # This is a simple way to ignore parsing errors on incomplete chunks
            pass

    def close(self):
        try:
            self._parser.Parse(f"</{self._root_tag}>".encode('utf-8'), True)
        except xml.parsers.expat.error:
            # Ignore final parsing errors if the XML is not perfectly formed
            pass
