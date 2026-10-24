import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'
import tseslint from 'typescript-eslint'

/**
 * Линтер ловит ошибки, а не стиль: рекомендованные правила ESLint и typescript-eslint,
 * для шаблонов Vue — essential (без правил оформления). Типы проверяет vue-tsc (npm run typecheck).
 */
export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: { parser: tseslint.parser },
    },
  },
  {
    files: ['**/*.{ts,vue}'],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // Имена и типы в TypeScript проверяет компилятор; no-undef не знает типов DOM (ScrollBehavior и т. п.)
      'no-undef': 'off',
      // _ в начале имени — намеренно неиспользуемый аргумент или переменная
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['*.config.{js,ts}', 'vite.config.ts'],
    languageOptions: { globals: globals.node },
  },
)
