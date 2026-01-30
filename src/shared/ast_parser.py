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
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.append(node.func.attr)
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
        self.current_package = self._extract_package(file_path)

        self.current_module_imports = set()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=file_path)
            entities = self._walk_tree(tree)

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

    def _walk_tree(self, tree: ast.AST) -> List[Dict[str, Any]]:
        entities = []

        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                self._handle_import_from(node)

            elif isinstance(node, ast.Import):
                self._handle_import(node)

            elif isinstance(node, ast.ClassDef):
                entities.extend(self._handle_class_with_context(node))

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                entity = self._handle_function(node)
                entity["parent_class"] = None
                entities.append(entity)

        return entities

    def _handle_class_with_context(self, node: ast.ClassDef) -> List[Dict[str, Any]]:
        entities = []

        # Push class context
        self.class_stack.append(node.name)

        class_entity = self._handle_class(node)
        entities.append(class_entity)

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = self._handle_function(item)
                func["parent_class"] = node.name
                entities.append(func)

        # Pop class context
        self.class_stack.pop()

        return entities


    def _handle_import(self, node: ast.Import) -> None:
        """Handle import statement."""
        for alias in node.names:
            module_name = alias.name
            self.current_module_imports.add(module_name)

    def _handle_import_from(self, node: ast.ImportFrom) -> None:
        """Handle from...import statement."""
        if node.module:
            self.current_module_imports.add(node.module)

    def _handle_class(self, node: ast.ClassDef) -> Dict[str, Any]:
        """
        Handle ClassDef node.

        Args:
            node: ClassDef AST node

        Returns:
            Class entity dictionary
        """
        docstring = ast.get_docstring(node)
        bases = [self._get_name(base) for base in node.bases]

        entity = {
            "type": "Class",
            "name": node.name,
            "module": self.current_file,
            "line_number": node.lineno,
            "docstring": docstring,
            "bases": bases,
            "package": self.current_package,
            "decorators": self._get_decorators(node),
        }
        logger.debug("Class extracted", name=node.name)

        return entity

    def _handle_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> Dict[str, Any]:

        docstring = ast.get_docstring(node)
        is_async = isinstance(node, ast.AsyncFunctionDef)

        visitor = CallVisitor()
        visitor.visit(node)

        # Extract parameters
        params = [arg.arg for arg in node.args.args]

        returns = ast.unparse(node.returns) if node.returns else None

        entity = {
            "type": "Function",
            "name": node.name,
            "module": self.current_file,
            "line_number": node.lineno,
            "docstring": docstring,
            "parameters": params,
            "returns": returns,
            "is_async": is_async,
            "package": self.current_package,
            "decorators": self._get_decorators(node),
            "calls": visitor.calls,   # ✅ now works
        }

        logger.debug("Function extracted", name=node.name, is_async=is_async)
        return entity


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
        # Find repo root (fastapi/)
        parts = file_path.replace("\\", "/").split("/")

        if "fastapi" not in parts:
            return ""

        idx = parts.index("fastapi")

        # fastapi/applications.py → fastapi.applications
        module_parts = parts[idx:]
        if module_parts[-1].endswith(".py"):
            module_parts[-1] = module_parts[-1][:-3]

        return ".".join(module_parts)



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
