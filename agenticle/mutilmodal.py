import os
import base64
import mimetypes
from typing import List, Dict, Type, Union, Any

class BaseInput:
    def __init__(self, input_path: str) -> None:
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"The file was not found: {input_path}")
        self.input_path = input_path
        self.filename = os.path.basename(input_path)

    def _get_media_type(self) -> str:
        media_type, _ = mimetypes.guess_type(self.input_path)
        return media_type or "application/octet-stream"

    def _process_content(self) -> List[Dict[str, Any]]:
        """
        Subclasses must implement this method to handle the core logic of reading
        and processing the file content.
        """
        raise NotImplementedError("Subclasses must implement the _process_content method.")

    def read_input(self, chunk_size: int = 4000, overlap: int = 200) -> List[Dict[str, Any]]:
        """
        Template method that structures the output. It calls the subclass's
        _process_content method to get the specific content and then chunks it if necessary.
        """
        processed_content = self._process_content()
        
        outputs = []
        
        # Check if the content is text and needs chunking
        is_text = len(processed_content) == 1 and processed_content[0].get("type") == "text"
        if is_text:
            text = processed_content[0]["text"]
            if len(text) > chunk_size:
                chunks = []
                start = 0
                while start < len(text):
                    end = start + chunk_size
                    chunks.append(text[start:end])
                    start += chunk_size - overlap
                
                total_chunks = len(chunks)
                for i, chunk in enumerate(chunks):
                    chunk_filename = f"{self.filename} (Part {i + 1}/{total_chunks})"
                    outputs.append({
                        "source": {
                            "type": "file",
                            "media_type": self._get_media_type(),
                            "filename": chunk_filename
                        },
                        "content": [{"type": "text", "text": chunk}]
                    })
                return outputs

        # For non-chunked text or other content types, return as a single item list
        outputs.append({
            "source": {
                "type": "file",
                "media_type": self._get_media_type(),
                "filename": self.filename
            },
            "content": processed_content
        })
        return outputs

class TextInput(BaseInput):
    def _process_content(self) -> List[Dict[str, Any]]:
        try:
            with open(self.input_path, 'r', encoding='utf-8') as f:
                text = f.read()
            return [{"type": "text", "text": text}]
        except UnicodeDecodeError:
            raise ValueError(f"File '{self.filename}' could not be read as text. It may be a binary file.")

class ImageInput(BaseInput):
    def _process_content(self) -> List[Dict[str, Any]]:
        with open(self.input_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        
        media_type = self._get_media_type()
        
        return [{
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{encoded_string}"
            }
        }]

_input_registry: Dict[str, Type[BaseInput]] = {
    ".txt": TextInput, ".md": TextInput, ".py": TextInput, ".json": TextInput,
    ".xml": TextInput, ".html": TextInput, ".css": TextInput, ".js": TextInput,
    ".jpg": ImageInput, ".jpeg": ImageInput, ".png": ImageInput, ".gif": ImageInput,
}

def register_input_processor(extensions: Union[str, List[str]], processor_class: Type[BaseInput]):
    if isinstance(extensions, str):
        extensions = [extensions]
    
    for ext in extensions:
        if not ext.startswith('.'):
            raise ValueError(f"Extension '{ext}' must start with a dot (e.g., '.txt').")
        _input_registry[ext.lower()] = processor_class

def get_input_processor(file_path: str) -> BaseInput:
    extension = os.path.splitext(file_path)[1].lower()
    processor_class = _input_registry.get(extension)
    
    if processor_class:
        return processor_class(file_path)
    else:
        # Fallback to TextInput for unknown extensions
        return TextInput(file_path)
