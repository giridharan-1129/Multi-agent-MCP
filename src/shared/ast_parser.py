"""
AST Parser Service.

WHAT: Parse Python files and extract code structure
WHY: Need to understand classes, functions, decorators, imports
HOW: Use Python's ast module to walk the syntax tree

Example:
    parser = ASTParser()
    entities = parser.parse_file("fastapi/main.py")
    for entity in entities:
        print(f"{entity['type']}: {entity['name']}")
"""

import ast
from typing import Any, Dict, List, Optional, Set

from .exceptions import FileParsingError
from .logger import get_logger

logger = get_logger(__name__)

class CallVisitor(ast.NodeVisitor):
    def __init__(self):
        self.calls = []

    def visit_Call(self, node: ast.Call):
        # foo()
        if isinstance(node.func, ast.Name):
            self.calls.append({
                "type": "function",
                "name": node.func.id,
            })

        # obj.foo()
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                self.calls.append({
                    "type": "method",
                    "object": node.func.value.id,
                    "name": node.func.attr,
                })

        self.generic_visit(node)


class ASTParser:
    """
    Parse Python files using Abstract Syntax Tree.

    Extracts classes, functions, imports, decorators, and docstrings
    from Python source code.

    Attributes:
        current_file: Currently parsing file path
        current_module_imports: Imports in current file
    """

    def __init__(self):
        """Initialize AST parser."""
        self.current_file: Optional[str] = None
        self.current_module_imports: Set[str] = set()
        self.instance_map: Dict[str, str] = {}

        self.class_stack: list[str] = []
        logger.debug("ASTParser initialized")


    def parse_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Parse a Python file and extract entities.

        Args:
            file_path: Path to Python file

        Returns:
            List of extracted entities (classes, functions, etc.)

        Raises:
            FileParsingError: If parsing fails
        """
        self.current_file = file_path
        self.instance_map = {}
        self.current_package = self._extract_package(file_path)

        self.current_module_imports = set()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=file_path)

            entities = []

            # --- MODULE NODE ---
            module_name = self._extract_module_name(file_path)
            if module_name:
                entities.append({
                    "type": "Module",
                    "name": module_name,
                    "module": self.current_file,
                    "file_path": file_path,
                    "package": self.current_package,
                })
                entities.append({
                    "type": "File",
                    "name": file_path,
                    "package": self.current_package,
                })
            # --- MODULE DOCSTRING ---
            module_docstring = ast.get_docstring(tree)
            if module_docstring:
                entities.append({
                    "type": "Docstring",
                    "name": f"{self.current_file}::docstring",
                    "scope": "module",
                    "content": module_docstring,
                    "module": self.current_file,
                    "package": self.current_package,
                })


            # --- EXISTING ENTITY EXTRACTION ---
            entities.extend(self._walk_tree(tree))


            logger.info(
                "File parsed successfully",
                file=file_path,
                entities_found=len(entities),
            )
            return entities

        except SyntaxError as e:
            logger.error(
                "Syntax error in file",
                file=file_path,
                line=e.lineno,
                error=str(e),
            )
            raise FileParsingError(
                file_path=file_path,
                error_detail=f"Syntax error at line {e.lineno}: {e.msg}",
            )
        except (OSError, UnicodeDecodeError) as e:
            logger.error("Failed to read file", file=file_path, error=str(e))
            raise FileParsingError(
                file_path=file_path,
                error_detail=str(e),
            )
    def _handle_assignment(self, node: ast.Assign) -> None:
        """
        Track instance creation like:
        app = FastAPI()
        router = APIRouter()
        """
        if isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name):
                class_name = func.id
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.instance_map[target.id] = class_name

    def _walk_tree(self, tree: ast.AST) -> List[Dict[str, Any]]:
        entities = []

        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                # Extract import entities
                import_entities = self._handle_import_from(node)
                entities.extend(import_entities)

            elif isinstance(node, ast.Import):
                # Extract import entities
                import_entities = self._handle_import(node)
                entities.extend(import_entities)
                
            elif isinstance(node, ast.Assign):
                self._handle_assignment(node)

            elif isinstance(node, ast.ClassDef):
                entities.extend(self._handle_class_with_context(node))

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_entities = self._handle_function(node)

                for e in function_entities:
                    if e["type"] == "Function":
                        e["parent_class"] = None

                entities.extend(function_entities)

        return entities
    def _extract_module_name(self, file_path: str) -> str:
        """
        Extract module name from file path.
        e.g., /path/to/fastapi/main.py -> fastapi.main
        """
        parts = file_path.replace("\\", "/").split("/")
        
        # Find the root package
        if "fastapi" not in parts:
            return ""
        
        idx = len(parts) - 1 - parts[::-1].index("fastapi")
        
        # Remove .py extension
        module_parts = parts[idx:-1]
        filename = parts[-1].replace(".py", "")
        
        if filename != "__init__":
            module_parts.append(filename)
        
        if not module_parts:
            return ""
        
        return ".".join(module_parts)
    def _handle_class_with_context(self, node: ast.ClassDef) -> List[Dict[str, Any]]:
        entities = []

        # Push class context
        self.class_stack.append(node.name)

        class_entities = self._handle_class(node)
        entities.extend(class_entities)

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_entities = self._handle_function(item)

                for e in function_entities:
                    if e["type"] == "Function":
                        e["parent_class"] = node.name

                entities.extend(function_entities)


        # Pop class context
        self.class_stack.pop()

        return entities


    def _handle_import(self, node: ast.Import) -> List[Dict[str, Any]]:
        """Handle import statement - extract Import entities."""
        entities = []
        
        for alias in node.names:
            module_name = alias.name
            import_name = alias.asname or alias.name
            self.current_module_imports.add(module_name)
            
            # Create Import entity
            entities.append({
                "type": "Import",
                "name": import_name,
                "module_name": module_name,
                "module": self.current_file,
                "line_number": node.lineno,
                "package": self.current_package,
            })
        
        return entities

    def _handle_import_from(self, node: ast.ImportFrom) -> List[Dict[str, Any]]:
        """Handle from...import statement - extract Import entities."""
        entities = []
        
        if node.module:
            self.current_module_imports.add(node.module)
        
        # Create Import entities for each imported name
        for alias in node.names:
            import_name = alias.asname or alias.name
            module_name = node.module or "__main__"
            
            entities.append({
                "type": "Import",
                "name": import_name,
                "module_name": module_name,
                "from_module": node.module,
                "module": self.current_file,
                "line_number": node.lineno,
                "package": self.current_package,
            })
        
        return entities

    def _handle_class(self, node: ast.ClassDef) -> List[Dict[str, Any]]:
        entities = []

        docstring = ast.get_docstring(node)
        if docstring:
            entities.append({
                "type": "Docstring",
                "name": f"{self.current_file}::{node.name}::docstring",
                "scope": "class",
                "content": docstring,
                "module": self.current_file,
                "package": self.current_package,
            })

        class_entity = {
            "type": "Class",
            "name": node.name,
            "module": self.current_file,
            "line_number": node.lineno,
            "docstring": docstring,
            "bases": [self._get_name(b) for b in node.bases],
            "bases_full": [ast.unparse(b) for b in node.bases],
            "package": self.current_package,
            "decorators": self._get_decorators(node),
        }

        # Extract decorators as entities
        for decorator_str in class_entity.get("decorators", []):
            entities.append({
                "type": "Decorator",
                "name": decorator_str,
                "module": self.current_file,
                "line_number": node.lineno,
                "package": self.current_package,
                "decorates": node.name,  # What it decorates
            })

        entities.append(class_entity)
        return entities



    def _handle_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> List[Dict[str, Any]]:

        entities = []

        docstring = ast.get_docstring(node)
        is_async = isinstance(node, ast.AsyncFunctionDef)

        # --- Calls ---
        visitor = CallVisitor()
        visitor.visit(node)

        # --- Parameters ---
        params = [arg.arg for arg in node.args.args]

        # --- Return annotation ---
        returns = ast.unparse(node.returns) if node.returns else None

        # --- Docstring entity ---
        if docstring:
            entities.append({
                "type": "Docstring",
                "name": f"{self.current_file}::{node.name}::docstring",
                "scope": "function",
                "content": docstring,
                "module": self.current_file,
                "package": self.current_package,
            })


        entity_type = "Method" if self.class_stack else "Function"

        function_entity = {
            "type": entity_type,
            "name": node.name,
            "module": self.current_file,
            "line_number": node.lineno,
            "docstring": docstring,
            "parameters": params,
            "returns": returns,
            "is_async": is_async,
            "package": self.current_package,
            "decorators": self._get_decorators(node),
            "calls": visitor.calls,
            "instance_map": self.instance_map.copy(),
            "parent_class": self.class_stack[-1] if self.class_stack else None,
        }
        for param in params:
            entities.append({
                "type": "Parameter",
                "name": f"{node.name}.{param}",
                "param_name": param,
                "function": node.name,
                "module": self.current_file,
                "package": self.current_package,
            })

                # Extract decorators as entities
        for decorator_str in function_entity.get("decorators", []):
            entities.append({
                "type": "Decorator",
                "name": decorator_str,
                "module": self.current_file,
                "line_number": node.lineno,
                "package": self.current_package,
                "decorates": node.name,  # What it decorates
            })

        if returns:
            entities.append({
                "type": "Type",
                "name": returns,
                "function": node.name,
                "module": self.current_file,
            })

        entities.append(function_entity)
        return entities



    def _get_decorators(self, node: ast.AST) -> List[str]:
        """
        Get decorators from a node.

        Args:
            node: AST node with decorator_list

        Returns:
            List of decorator names
        """
        decorators = []
        if hasattr(node, "decorator_list"):
            for decorator in node.decorator_list:
                decorator_name = ast.unparse(decorator)
                decorators.append(decorator_name)
        return decorators

    def _get_name(self, node: ast.AST) -> str:
        """
        Get name from various AST node types.

        Args:
            node: AST node

        Returns:
            Name string
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return ast.unparse(node)
        elif isinstance(node, ast.Constant):
            return str(node.value)
        else:
            return ast.unparse(node)

    def _extract_package(self, file_path: str) -> str:
        parts = file_path.replace("\\", "/").split("/")

        # Find the *project* fastapi directory
        if "fastapi" not in parts:
            return ""

        # Use the LAST occurrence of "fastapi"
        idx = len(parts) - 1 - parts[::-1].index("fastapi")

        # Everything after this fastapi/ is the Python package
        package_parts = parts[idx:-1]

        if not package_parts:
            return ""

        return ".".join(package_parts)






    def extract_imports(self, entities: List[Dict[str, Any]]) -> Set[str]:
        """
        Extract all imports from entities.

        Args:
            entities: List of parsed entities

        Returns:
            Set of import modules
        """
        return self.current_module_imports

    def get_entity_by_name(
        self,
        name: str,
        entities: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Find entity by name.

        Args:
            name: Entity name to find
            entities: List of entities to search

        Returns:
            Entity if found, None otherwise
        """
        for entity in entities:
            if entity.get("name") == name:
                return entity
        return None


# Global parser instance
ast_parser: Optional[ASTParser] = None


def init_parser() -> ASTParser:
    """
    Initialize AST parser.

    Returns:
        ASTParser instance
    """
    global ast_parser
    ast_parser = ASTParser()
    return ast_parser


def get_parser() -> ASTParser:
    """
    Get initialized parser.

    Returns:
        ASTParser instance
    """
    global ast_parser
    if not ast_parser:
        ast_parser = ASTParser()
    return ast_parser
