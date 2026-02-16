from __future__ import annotations

from midori_compiler import ast
from midori_compiler.errors import MidoriError
from midori_compiler.lexer import Lexer
from midori_compiler.span import Span
from midori_compiler.token import Token, TokenKind


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.i = 0

    @classmethod
    def from_source(cls, source: str, file: str = "<input>") -> Parser:
        return cls(Lexer(source, file).tokenize())

    def parse(self) -> ast.Program:
        items: list[ast.Item] = []
        self._skip_separators()
        while not self._check(TokenKind.EOF):
            items.append(self._parse_item())
            self._skip_separators()
        return ast.Program(span=self._span_from(items), items=items)

    def _parse_item(self) -> ast.Item:
        is_pub = self._match(TokenKind.PUB)
        is_task = self._match(TokenKind.TASK)
        if self._match(TokenKind.IMPORT):
            if is_pub or is_task:
                raise self._error_here("`import` cannot be prefixed with pub/task")
            return self._parse_import_decl()
        if self._match(TokenKind.FN):
            return self._parse_fn(is_pub=is_pub, is_task=is_task)
        if self._match(TokenKind.EXTERN):
            return self._parse_extern_fn()
        if self._match(TokenKind.STRUCT):
            return self._parse_struct()
        if self._match(TokenKind.ENUM):
            return self._parse_enum()
        if self._match(TokenKind.TRAIT):
            return self._parse_trait()
        if self._match(TokenKind.ERROR):
            return self._parse_error_decl()
        raise self._error_here(
            "expected item", "start with import/fn/struct/enum/trait/extern/error"
        )

    def _parse_import_decl(self) -> ast.ImportDecl:
        path = self._expect(TokenKind.STRING, "expected import path string, e.g. \"./util.mdr\"")
        return ast.ImportDecl(span=path.span, path=path.lexeme.strip('"'))

    def _parse_fn(self, *, is_pub: bool, is_task: bool) -> ast.FunctionDecl:
        name = self._expect(TokenKind.IDENT, "expected function name")
        generic_params = self._parse_generic_params()
        self._expect(TokenKind.LPAREN, "expected '('")
        params = self._parse_params()
        self._expect(TokenKind.RPAREN, "expected ')'")
        ret = self._parse_optional_return()
        body = self._parse_block()
        return ast.FunctionDecl(
            span=self._span(name.span, body.span),
            name=name.lexeme,
            generic_params=generic_params,
            params=params,
            return_type=ret,
            body=body,
            is_task=is_task,
            is_pub=is_pub,
        )

    def _parse_extern_fn(self) -> ast.ExternFunctionDecl:
        abi = "C"
        if self._check(TokenKind.STRING):
            abi = self._advance().lexeme.strip('"')
        self._expect(TokenKind.FN, "expected fn in extern declaration")
        name = self._expect(TokenKind.IDENT, "expected extern function name")
        self._expect(TokenKind.LPAREN, "expected '('")
        params = self._parse_params()
        self._expect(TokenKind.RPAREN, "expected ')'")
        ret = self._parse_optional_return()
        self._skip_separators()
        return ast.ExternFunctionDecl(
            span=self._span(name.span, self._prev().span),
            abi=abi,
            name=name.lexeme,
            params=params,
            return_type=ret,
        )

    def _parse_struct(self) -> ast.StructDecl:
        name = self._expect(TokenKind.IDENT, "expected struct name")
        self._expect(TokenKind.LBRACE, "expected '{'")
        fields: list[ast.StructField] = []
        self._skip_separators()
        while not self._check(TokenKind.RBRACE):
            field_name = self._expect(TokenKind.IDENT, "expected field name")
            self._expect(TokenKind.COLON, "expected ':'")
            ty = self._parse_type()
            fields.append(
                ast.StructField(
                    span=self._span(field_name.span, ty.span),
                    name=field_name.lexeme,
                    ty=ty,
                )
            )
            self._match(TokenKind.COMMA)
            self._skip_separators()
        end = self._expect(TokenKind.RBRACE, "expected '}'")
        return ast.StructDecl(span=self._span(name.span, end.span), name=name.lexeme, fields=fields)

    def _parse_enum(self) -> ast.EnumDecl:
        name = self._expect(TokenKind.IDENT, "expected enum name")
        self._expect(TokenKind.LBRACE, "expected '{'")
        variants: list[ast.EnumVariant] = []
        self._skip_separators()
        while not self._check(TokenKind.RBRACE):
            var_name = self._expect(TokenKind.IDENT, "expected variant name")
            fields: list[ast.StructField] = []
            if self._match(TokenKind.LPAREN):
                self._skip_separators()
                while not self._check(TokenKind.RPAREN):
                    f_name = self._expect(TokenKind.IDENT, "expected variant field name")
                    self._expect(TokenKind.COLON, "expected ':'")
                    ty = self._parse_type()
                    fields.append(
                        ast.StructField(
                            span=self._span(f_name.span, ty.span),
                            name=f_name.lexeme,
                            ty=ty,
                        )
                    )
                    if not self._match(TokenKind.COMMA):
                        break
                self._expect(TokenKind.RPAREN, "expected ')'")
            variants.append(
                ast.EnumVariant(
                    span=self._span(var_name.span, self._prev().span),
                    name=var_name.lexeme,
                    fields=fields,
                )
            )
            self._match(TokenKind.COMMA)
            self._skip_separators()
        end = self._expect(TokenKind.RBRACE, "expected '}'")
        return ast.EnumDecl(
            span=self._span(name.span, end.span), name=name.lexeme, variants=variants
        )

    def _parse_trait(self) -> ast.TraitDecl:
        name = self._expect(TokenKind.IDENT, "expected trait name")
        self._expect(TokenKind.LBRACE, "expected '{'")
        methods: list[ast.FunctionSig] = []
        self._skip_separators()
        while not self._check(TokenKind.RBRACE):
            self._expect(TokenKind.FN, "expected fn method declaration")
            m_name = self._expect(TokenKind.IDENT, "expected method name")
            generic_params = self._parse_generic_params()
            self._expect(TokenKind.LPAREN, "expected '('")
            params = self._parse_params()
            self._expect(TokenKind.RPAREN, "expected ')'")
            ret = self._parse_optional_return()
            methods.append(
                ast.FunctionSig(
                    span=self._span(m_name.span, self._prev().span),
                    name=m_name.lexeme,
                    generic_params=generic_params,
                    params=params,
                    return_type=ret,
                )
            )
            self._skip_separators()
        end = self._expect(TokenKind.RBRACE, "expected '}'")
        return ast.TraitDecl(
            span=self._span(name.span, end.span), name=name.lexeme, methods=methods
        )

    def _parse_error_decl(self) -> ast.ErrorDecl:
        name = self._expect(TokenKind.IDENT, "expected custom error name")
        return ast.ErrorDecl(span=name.span, name=name.lexeme)

    def _parse_params(self) -> list[ast.Param]:
        params: list[ast.Param] = []
        self._skip_separators()
        while not self._check(TokenKind.RPAREN):
            p_name = self._expect(TokenKind.IDENT, "expected parameter name")
            self._expect(TokenKind.COLON, "expected ':'")
            p_ty = self._parse_type()
            params.append(
                ast.Param(span=self._span(p_name.span, p_ty.span), name=p_name.lexeme, ty=p_ty)
            )
            if not self._match(TokenKind.COMMA):
                break
            self._skip_separators()
        return params

    def _parse_optional_return(self) -> ast.TypeRef | None:
        if self._match(TokenKind.ARROW):
            return self._parse_type()
        return None

    def _parse_generic_params(self) -> list[str]:
        params: list[str] = []
        if not self._match(TokenKind.LBRACKET):
            return params
        while True:
            params.append(self._expect(TokenKind.IDENT, "expected generic parameter name").lexeme)
            if self._match(TokenKind.COLON):
                self._expect(TokenKind.IDENT, "expected trait bound name")
            if self._match(TokenKind.COMMA):
                continue
            self._expect(TokenKind.RBRACKET, "expected ']'")
            break
        return params

    def _parse_type(self) -> ast.TypeRef:
        is_ref = False
        is_mut_ref = False
        is_ptr = False
        is_mut_ptr = False
        if self._match(TokenKind.AMP):
            is_ref = True
            if self._check(TokenKind.IDENT) and self._peek().lexeme == "mut":
                self._advance()
                is_mut_ref = True
        if self._match(TokenKind.STAR):
            is_ptr = True
            if self._check(TokenKind.IDENT) and self._peek().lexeme == "mut":
                self._advance()
                is_mut_ptr = True
        name = self._expect(TokenKind.IDENT, "expected type name")
        args: list[ast.TypeRef] = []
        if self._match(TokenKind.LBRACKET):
            while True:
                args.append(self._parse_type())
                if self._match(TokenKind.COMMA):
                    continue
                self._expect(TokenKind.RBRACKET, "expected ']'")
                break
        return ast.TypeRef(
            span=self._span(name.span, self._prev().span),
            name=name.lexeme,
            args=args,
            is_ref=is_ref,
            is_mut_ref=is_mut_ref,
            is_ptr=is_ptr,
            is_mut_ptr=is_mut_ptr,
        )

    def _parse_block(self) -> ast.BlockExpr:
        start = self._expect(TokenKind.LBRACE, "expected '{'")
        self._skip_separators()
        statements: list[ast.Stmt] = []
        tail: ast.Expr | None = None
        while not self._check(TokenKind.RBRACE):
            if self._starts_stmt():
                statements.append(self._parse_stmt())
                self._skip_separators()
                continue
            expr = self._parse_expr()
            if self._match(TokenKind.SEMI):
                statements.append(ast.ExprStmt(span=expr.span, expr=expr))
                self._skip_separators()
            elif self._check(TokenKind.NEWLINE):
                self._advance()
                if self._check(TokenKind.RBRACE):
                    tail = expr
                    break
                statements.append(ast.ExprStmt(span=expr.span, expr=expr))
                self._skip_separators()
            else:
                tail = expr
                break
        end = self._expect(TokenKind.RBRACE, "expected '}'")
        return ast.BlockExpr(
            span=self._span(start.span, end.span), statements=statements, tail=tail
        )

    def _starts_stmt(self) -> bool:
        return self._check_any(
            TokenKind.LET, TokenKind.VAR, TokenKind.RETURN, TokenKind.BREAK, TokenKind.CONTINUE
        )

    def _parse_stmt(self) -> ast.Stmt:
        if self._match(TokenKind.LET):
            return self._parse_let(mutable=False)
        if self._match(TokenKind.VAR):
            return self._parse_let(mutable=True)
        if self._match(TokenKind.RETURN):
            if self._check_any(TokenKind.SEMI, TokenKind.NEWLINE, TokenKind.RBRACE):
                return ast.ReturnStmt(span=self._prev().span, expr=None)
            expr = self._parse_expr()
            return ast.ReturnStmt(span=self._span(self._prev().span, expr.span), expr=expr)
        if self._match(TokenKind.BREAK):
            expr = (
                None
                if self._check_any(TokenKind.SEMI, TokenKind.NEWLINE, TokenKind.RBRACE)
                else self._parse_expr()
            )
            span = self._prev().span if expr is None else self._span(self._prev().span, expr.span)
            return ast.BreakStmt(span=span, expr=expr)
        if self._match(TokenKind.CONTINUE):
            return ast.ContinueStmt(span=self._prev().span)
        raise self._error_here("expected statement")

    def _parse_let(self, *, mutable: bool) -> ast.LetStmt:
        name = self._expect(TokenKind.IDENT, "expected variable name")
        ty = None
        inferred = False
        if self._match(TokenKind.COLONEQ):
            inferred = True
        else:
            if self._match(TokenKind.COLON):
                ty = self._parse_type()
            self._expect(TokenKind.EQ, "expected '=' or ':='")
        expr = self._parse_expr()
        return ast.LetStmt(
            span=self._span(name.span, expr.span),
            name=name.lexeme,
            ty=ty,
            expr=expr,
            mutable=mutable,
            inferred=inferred,
        )

    def _parse_expr(self) -> ast.Expr:
        return self._parse_assignment()

    def _parse_assignment(self) -> ast.Expr:
        expr = self._parse_range()
        if self._match_any(
            TokenKind.EQ,
            TokenKind.PLUSEQ,
            TokenKind.MINUSEQ,
            TokenKind.STAREQ,
            TokenKind.SLASHEQ,
            TokenKind.PERCENTEQ,
        ):
            op = self._prev().lexeme
            value = self._parse_assignment()
            return ast.AssignExpr(
                span=self._span(expr.span, value.span), target=expr, op=op, value=value
            )
        return expr

    def _parse_range(self) -> ast.Expr:
        expr = self._parse_or()
        if self._match(TokenKind.DOTDOT):
            end = self._parse_or()
            return ast.RangeExpr(
                span=self._span(expr.span, end.span), start=expr, end=end, inclusive=False
            )
        if self._match(TokenKind.DOTDOTEQ):
            end = self._parse_or()
            return ast.RangeExpr(
                span=self._span(expr.span, end.span), start=expr, end=end, inclusive=True
            )
        return expr

    def _parse_or(self) -> ast.Expr:
        return self._binop(self._parse_and, {TokenKind.OROR})

    def _parse_and(self) -> ast.Expr:
        return self._binop(self._parse_equality, {TokenKind.ANDAND})

    def _parse_equality(self) -> ast.Expr:
        return self._binop(self._parse_compare, {TokenKind.EQEQ, TokenKind.NE})

    def _parse_compare(self) -> ast.Expr:
        return self._binop(
            self._parse_term, {TokenKind.LT, TokenKind.LE, TokenKind.GT, TokenKind.GE}
        )

    def _parse_term(self) -> ast.Expr:
        return self._binop(self._parse_factor, {TokenKind.PLUS, TokenKind.MINUS})

    def _parse_factor(self) -> ast.Expr:
        return self._binop(self._parse_unary, {TokenKind.STAR, TokenKind.SLASH, TokenKind.PERCENT})

    def _parse_unary(self) -> ast.Expr:
        if self._match_any(
            TokenKind.BANG, TokenKind.MINUS, TokenKind.AWAIT, TokenKind.SPAWN, TokenKind.AMP
        ):
            op = self._prev()
            op_lexeme = op.lexeme
            if (
                op.kind is TokenKind.AMP
                and self._check(TokenKind.IDENT)
                and self._peek().lexeme == "mut"
            ):
                self._advance()
                op_lexeme = "&mut"
            expr = self._parse_unary()
            if op.kind is TokenKind.AWAIT:
                return ast.AwaitExpr(span=self._span(op.span, expr.span), expr=expr)
            if op.kind is TokenKind.SPAWN:
                return ast.SpawnExpr(span=self._span(op.span, expr.span), expr=expr)
            return ast.UnaryExpr(span=self._span(op.span, expr.span), op=op_lexeme, expr=expr)
        return self._parse_postfix()

    def _parse_postfix(self) -> ast.Expr:
        expr = self._parse_primary()
        while True:
            if self._match(TokenKind.LPAREN):
                args: list[ast.Expr] = []
                if not self._check(TokenKind.RPAREN):
                    while True:
                        args.append(self._parse_expr())
                        if not self._match(TokenKind.COMMA):
                            break
                end = self._expect(TokenKind.RPAREN, "expected ')'")
                expr = ast.CallExpr(span=self._span(expr.span, end.span), callee=expr, args=args)
                continue
            if self._match(TokenKind.QUESTION):
                expr = ast.PostfixTryExpr(span=self._span(expr.span, self._prev().span), expr=expr)
                continue
            break
        return expr

    def _parse_primary(self) -> ast.Expr:
        if self._match_any(
            TokenKind.INT,
            TokenKind.FLOAT,
            TokenKind.STRING,
            TokenKind.CHAR,
            TokenKind.TRUE,
            TokenKind.FALSE,
        ):
            tok = self._prev()
            return ast.LiteralExpr(span=tok.span, value=tok.lexeme, kind=tok.kind.name.lower())
        if self._match(TokenKind.IDENT):
            ident = self._prev()
            if self._check(TokenKind.LBRACE) and ident.lexeme[:1].isupper():
                self._advance()
                fields: list[ast.FieldInit] = []
                while not self._check(TokenKind.RBRACE):
                    f_name = self._expect(TokenKind.IDENT, "expected field name")
                    self._expect(TokenKind.COLON, "expected ':'")
                    value = self._parse_expr()
                    fields.append(
                        ast.FieldInit(
                            span=self._span(f_name.span, value.span), name=f_name.lexeme, expr=value
                        )
                    )
                    if not self._match(TokenKind.COMMA):
                        break
                end = self._expect(TokenKind.RBRACE, "expected '}'")
                return ast.StructInitExpr(
                    span=self._span(ident.span, end.span), name=ident.lexeme, fields=fields
                )
            return ast.IdentifierExpr(span=ident.span, name=ident.lexeme)
        if self._match(TokenKind.LPAREN):
            expr = self._parse_expr()
            self._expect(TokenKind.RPAREN, "expected ')'")
            return expr
        if self._check(TokenKind.LBRACE):
            return self._parse_block()
        if self._match(TokenKind.IF):
            return self._parse_if_expr()
        if self._match(TokenKind.MATCH):
            return self._parse_match_expr()
        if self._match(TokenKind.UNSAFE):
            marker = self._prev()
            block = self._parse_block()
            return ast.UnsafeExpr(span=self._span(marker.span, block.span), block=block)
        if self._match(TokenKind.RAISE):
            marker = self._prev()
            kind = self._expect(TokenKind.IDENT, "expected custom error name after raise")
            self._expect(TokenKind.LPAREN, "expected '(' after custom error name")
            message = self._parse_expr()
            end = self._expect(TokenKind.RPAREN, "expected ')'")
            return ast.RaiseExpr(
                span=self._span(marker.span, end.span), kind=kind.lexeme, message=message
            )
        raise self._error_here("expected expression")

    def _parse_if_expr(self) -> ast.IfExpr:
        cond = self._parse_expr()
        then_block = self._parse_block()
        else_expr: ast.Expr | None = None
        if self._match(TokenKind.ELSE):
            if self._match(TokenKind.IF):
                else_expr = self._parse_if_expr()
            elif self._check(TokenKind.LBRACE):
                else_expr = self._parse_block()
            else:
                else_expr = self._parse_expr()
        end = else_expr.span if else_expr else then_block.span
        return ast.IfExpr(
            span=self._span(cond.span, end),
            condition=cond,
            then_block=then_block,
            else_branch=else_expr,
        )

    def _parse_match_expr(self) -> ast.MatchExpr:
        target = self._parse_expr()
        self._expect(TokenKind.LBRACE, "expected '{' after match expression")
        arms: list[ast.MatchArm] = []
        self._skip_separators()
        while not self._check(TokenKind.RBRACE):
            pattern = self._parse_pattern()
            self._expect(TokenKind.FATARROW, "expected '=>' in match arm")
            expr = self._parse_expr()
            arms.append(
                ast.MatchArm(span=self._span(pattern.span, expr.span), pattern=pattern, expr=expr)
            )
            self._match(TokenKind.COMMA)
            self._skip_separators()
        end = self._expect(TokenKind.RBRACE, "expected '}'")
        return ast.MatchExpr(span=self._span(target.span, end.span), expr=target, arms=arms)

    def _parse_pattern(self) -> ast.Pattern:
        if self._match(TokenKind.IDENT):
            tok = self._prev()
            if tok.lexeme == "_":
                return ast.WildcardPattern(span=tok.span)
            if self._match(TokenKind.LPAREN):
                fields: list[str] = []
                while not self._check(TokenKind.RPAREN):
                    fields.append(self._expect(TokenKind.IDENT, "expected pattern field").lexeme)
                    if not self._match(TokenKind.COMMA):
                        break
                self._expect(TokenKind.RPAREN, "expected ')'")
                return ast.VariantPattern(
                    span=self._span(tok.span, self._prev().span), name=tok.lexeme, fields=fields
                )
            return ast.NamePattern(span=tok.span, name=tok.lexeme)
        if self._match_any(
            TokenKind.INT,
            TokenKind.FLOAT,
            TokenKind.STRING,
            TokenKind.CHAR,
            TokenKind.TRUE,
            TokenKind.FALSE,
        ):
            tok = self._prev()
            return ast.LiteralPattern(span=tok.span, value=tok.lexeme)
        raise self._error_here("expected pattern")

    def _binop(self, next_fn, ops: set[TokenKind]) -> ast.Expr:
        expr = next_fn()
        while self._match_any(*ops):
            op = self._prev()
            right = next_fn()
            expr = ast.BinaryExpr(
                span=self._span(expr.span, right.span), left=expr, op=op.lexeme, right=right
            )
        return expr

    def _skip_separators(self) -> None:
        while self._match_any(TokenKind.NEWLINE, TokenKind.SEMI):
            pass

    def _expect(self, kind: TokenKind, message: str) -> Token:
        if self._check(kind):
            return self._advance()
        raise self._error_here(message)

    def _match(self, kind: TokenKind) -> bool:
        if self._check(kind):
            self._advance()
            return True
        return False

    def _match_any(self, *kinds: TokenKind) -> bool:
        for kind in kinds:
            if self._check(kind):
                self._advance()
                return True
        return False

    def _check(self, kind: TokenKind) -> bool:
        return self._peek().kind is kind

    def _check_any(self, *kinds: TokenKind) -> bool:
        return any(self._check(k) for k in kinds)

    def _advance(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def _peek(self) -> Token:
        return self.tokens[self.i]

    def _prev(self) -> Token:
        return self.tokens[self.i - 1]

    def _span(self, a: Span, b: Span) -> Span:
        return Span(file=a.file, start=a.start, end=b.end, line=a.line, col=a.col)

    def _span_from(self, nodes: list[ast.Node]) -> Span:
        if not nodes:
            return self._peek().span
        return self._span(nodes[0].span, nodes[-1].span)

    def _error_here(self, message: str, hint: str | None = None) -> MidoriError:
        return MidoriError(span=self._peek().span, message=message, hint=hint)
