import {Fragment, useCallback, useEffect} from 'react';
import * as Sentry from '@sentry/react';

import ContextDataSection from 'sentry/components/events/contexts/contextDataSection';
import {useHasNewTagsUI} from 'sentry/components/events/eventTags/util';
import type {Event, EventContexts as EventContextValues} from 'sentry/types/event';
import type {Group} from 'sentry/types/group';
import {objectIsEmpty} from 'sentry/utils';
import useProjects from 'sentry/utils/useProjects';

import {Chunk} from './chunk';

type Props = {
  event: Event;
  group?: Group;
};

interface UnknownContextValue {
  [key: string]: any;
  type: 'default';
}

/**
 * Catch-all for context values, known and unknown
 */
export type ContextValue =
  | EventContextValues[keyof EventContextValues]
  | UnknownContextValue;

export interface ContextItem {
  alias: string;
  type: string;
  value: ContextValue;
}

export function getOrderedContextItems(event): ContextItem[] {
  const {user, contexts} = event;

  const {feedback, response, ...otherContexts} = contexts ?? {};
  const orderedContext: [ContextItem['alias'], ContextValue][] = [
    ['response', response],
    ['feedback', feedback],
    ['user', user],
    ...Object.entries(otherContexts),
  ];
  // For these context keys, use 'key' as 'type' rather than 'value.type'
  const overrideTypes = new Set(['response', 'feedback', 'user']);
  const items = orderedContext
    .filter(([_k, ctxValue]) => {
      const contextKeys = Object.keys(ctxValue ?? {});
      const isInvalid =
        // Empty context
        contextKeys.length === 0 ||
        // Empty aside from 'type' key
        (contextKeys.length === 1 && contextKeys[0] === 'type');
      return !isInvalid;
    })
    .map<ContextItem>(([alias, ctx]) => ({
      alias,
      type: overrideTypes.has(ctx.type) ? ctx : ctx?.type,
      value: ctx,
    }));

  return items;
}

export function EventContexts({event, group}: Props) {
  const hasNewTagsUI = useHasNewTagsUI();
  const {projects} = useProjects();
  const project = projects.find(p => p.id === event.projectID);
  const {user, contexts, sdk} = event;

  const {feedback, response, ...otherContexts} = contexts ?? {};

  const usingOtel = useCallback(
    () => otherContexts.otel !== undefined,
    [otherContexts.otel]
  );

  useEffect(() => {
    const transaction = Sentry.getActiveTransaction();
    if (transaction && usingOtel()) {
      transaction.tags.otel_event = true;
      transaction.tags.otel_sdk = sdk?.name;
      transaction.tags.otel_sdk_version = sdk?.version;
    }
  }, [usingOtel, sdk]);

  if (hasNewTagsUI) {
    return <ContextDataSection event={event} group={group} project={project} />;
  }

  return (
    <Fragment>
      {!objectIsEmpty(response) && (
        <Chunk
          key="response"
          type="response"
          alias="response"
          group={group}
          event={event}
          value={response}
        />
      )}
      {!objectIsEmpty(feedback) && (
        <Chunk
          key="feedback"
          type="feedback"
          alias="feedback"
          group={group}
          event={event}
          value={feedback}
        />
      )}
      {user && !objectIsEmpty(user) && (
        <Chunk
          key="user"
          type="user"
          alias="user"
          group={group}
          event={event}
          value={user}
        />
      )}
      {Object.entries(otherContexts).map(([key, value]) => (
        <Chunk
          key={key}
          type={value?.type ?? ''}
          alias={key}
          group={group}
          event={event}
          value={value}
        />
      ))}
    </Fragment>
  );
}
