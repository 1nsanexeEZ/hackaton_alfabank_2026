/**
 * Схема маршрута из BPMN 2.0 XML (GET /workflows/{code}/diagram): узлы, переходы и кто выполняет
 * задачу. Координаты BPMNDI не берём — упрощённую схему по этапам раскладываем сами (stages.ts).
 */

const BPMN_NS = 'http://www.omg.org/spec/BPMN/20100524/MODEL'
const CAMUNDA_NS = 'http://camunda.org/schema/1.0/bpmn'

export interface BpmnNode {
  id: string
  /** Тип элемента BPMN: startEvent, endEvent, serviceTask, userTask, exclusiveGateway… */
  type: string
  name: string
  /** Кто выполняет пользовательскую задачу: client, underwriter */
  candidateGroups: string | null
}

export interface BpmnFlow {
  source: string
  target: string
  /** Условие перехода, например `outcome == "REJECT"`; нет — переход по умолчанию или единственный */
  condition: string | null
}

export interface Workflow {
  code: string
  /** «Бизнес-ипотека: решение всегда за андеррайтером» */
  name: string
  nodes: ReadonlyMap<string, BpmnNode>
  flows: readonly BpmnFlow[]
}

export const isGateway = (node: BpmnNode) => node.type.endsWith('Gateway')
export const isStartEvent = (node: BpmnNode) => node.type === 'startEvent'
export const isEndEvent = (node: BpmnNode) => node.type === 'endEvent'

export function parseWorkflow(xml: string): Workflow {
  const document = new DOMParser().parseFromString(xml, 'application/xml')
  const process = document.getElementsByTagNameNS(BPMN_NS, 'process')[0]
  if (document.getElementsByTagName('parsererror').length || !process) {
    throw new Error('Не удалось прочитать схему маршрута')
  }

  const nodes = new Map<string, BpmnNode>()
  const flows: BpmnFlow[] = []
  for (const element of Array.from(process.children)) {
    if (element.namespaceURI !== BPMN_NS) continue
    const id = element.getAttribute('id')
    if (!id) continue
    if (element.localName === 'sequenceFlow') {
      const source = element.getAttribute('sourceRef')
      const target = element.getAttribute('targetRef')
      const condition = element.getElementsByTagNameNS(BPMN_NS, 'conditionExpression')[0]?.textContent?.trim() || null
      if (source && target) flows.push({ source, target, condition })
      continue
    }
    nodes.set(id, {
      id,
      type: element.localName,
      name: element.getAttribute('name') ?? id,
      candidateGroups: element.getAttributeNS(CAMUNDA_NS, 'candidateGroups') || element.getAttribute('camunda:candidateGroups'),
    })
  }

  return { code: process.getAttribute('id') ?? '', name: process.getAttribute('name') ?? '', nodes, flows }
}
